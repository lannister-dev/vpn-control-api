from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from shared.nats.client import NatsClient

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import EntryRoutingConfig, get_settings
from services.nodes.constants import ROLE_BACKEND, ROLE_ENTRY, ROLE_WHITELIST_ENTRY
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.routing.entry.constants import KV_STATS_BUCKET
from services.routing.entry.exceptions import UnknownBackendTagError
from services.routing.entry.schemas import (
    EntryRoutingBackend,
    EntryRoutingReality,
    EntryRoutingRule,
    EntryRoutingSpec,
    EntryRoutingUrltestGroup,
    EntryRoutingUser,
    KeyRoutingOverrideOut,
    OverrideChange,
    RoutingBackendOut,
    RoutingKeyRowOut,
    RoutingLiveStatsByBackend,
    RoutingLiveStatsByEntry,
    RoutingStateOut,
)
from services.vpn.keys.repository import VpnKeyRepository
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger
from shared.utils.node_display import effective_zone

logger = StructuredLogger(logging.getLogger("entry-routing-service"))


class EntryRoutingService:
    def __init__(self, session: AsyncSession, *, config: EntryRoutingConfig):
        self.session = session
        self.config = config
        self.node_repo = VpnNodeRepository(session)
        self.key_repo = VpnKeyRepository(session)
        from services.routes.repository import RouteRepository
        self.route_repo = RouteRepository(session)

    async def list_target_nodes(self) -> list[VpnNode]:
        all_nodes = await self.node_repo.list()
        return [n for n in all_nodes if n.role in (ROLE_ENTRY, ROLE_WHITELIST_ENTRY)]

    async def build_spec_for_node(self, node_id: UUID) -> EntryRoutingSpec | None:
        node = await self.node_repo.get_by_id(node_id)
        if node is None:
            return None
        if node.role not in (ROLE_ENTRY, ROLE_WHITELIST_ENTRY):
            return None

        keys = await self.key_repo.list_all_active()
        users = [
            EntryRoutingUser(uuid=key.client_id)
            for key in keys
            if key.client_id
        ]
        overrides = {
            key.client_id: key.entry_routing_override_backend_tag
            for key in keys
            if key.client_id and key.entry_routing_override_backend_tag
        }
        backend_nodes = await self._candidate_backend_nodes_for_zone(node)
        backends, rules, urltest_groups, final_outbound = self._materialize_outbounds_and_rules(
            users, backend_nodes, overrides,
        )
        return EntryRoutingSpec(
            node_id=str(node.id),
            listen_port=self.config.listen_port,
            reality=EntryRoutingReality(
                private_key=self.config.reality_private_key,
                short_id=self.config.reality_short_id,
                server_name=self.config.reality_server_name,
                handshake_server=self.config.reality_handshake_server,
                handshake_port=self.config.reality_handshake_port,
            ),
            users=users,
            backends=backends,
            rules=rules,
            urltest_groups=urltest_groups,
            final_outbound=final_outbound,
        )

    async def _candidate_backend_nodes_for_zone(self, entry: VpnNode) -> list[VpnNode]:
        if self.config.backend_use_wg:
            if not self._has_wg_addr(entry):
                return []
        else:
            if not self.config.backend_service_uuid:
                return []
            if not self.config.backend_reality_public_key:
                return []
        route_backend_ids: list[UUID] = []
        try:
            route_backend_ids = await self.route_repo.list_backend_ids_for_entry(
                entry_node_id=entry.id,
            )
        except Exception:
            logger.exception("entry_routing_route_filter_failed", entry_id=str(entry.id))
        if route_backend_ids:
            route_id_set = set(route_backend_ids)
            nodes = await self.node_repo.list_by_ids(route_backend_ids)
            return [
                n for n in nodes
                if n.id in route_id_set
                and n.role == ROLE_BACKEND
                and n.is_enabled
                and not n.is_draining
                and self._has_reachable_addr(n)
            ]
        zone = effective_zone(explicit_zone=entry.zone, region=entry.region)
        all_nodes = await self.node_repo.list()
        return [
            n for n in all_nodes
            if n.role == ROLE_BACKEND
            and n.is_enabled
            and not n.is_draining
            and effective_zone(explicit_zone=n.zone, region=n.region) == zone
            and self._has_reachable_addr(n)
        ]

    async def _build_backends_for_zone(self, entry: VpnNode) -> list[EntryRoutingBackend]:
        nodes = await self._candidate_backend_nodes_for_zone(entry)
        return [
            self._make_outbound(n, tag=self._backend_node_tag(n), uuid=self.config.backend_service_uuid)
            for n in nodes
        ]

    def _has_reachable_addr(self, node: VpnNode) -> bool:
        if self.config.backend_use_wg:
            return self._has_wg_addr(node)
        return bool(node.reality_ip or node.public_domain)

    @staticmethod
    def _has_wg_addr(node: VpnNode) -> bool:
        ip = (node.internal_wg_ip or "").strip()
        return bool(ip) and not ip.startswith("0.")

    @staticmethod
    def _backend_node_tag(node: VpnNode) -> str:
        return f"backend-{node.name}"

    @staticmethod
    def _user_outbound_tag(node_name: str, client_id: str) -> str:
        return f"b-{client_id}-{node_name}"

    def _make_outbound(
        self, node: VpnNode, *, tag: str, uuid: str,
    ) -> EntryRoutingBackend:
        if self.config.backend_use_wg:
            return EntryRoutingBackend(
                tag=tag,
                node_name=node.name,
                backend_node_id=node.id,
                server=node.internal_wg_ip,
                server_port=self.config.backend_wg_port,
                uuid=uuid,
                flow="",
            )
        server = node.reality_ip or node.public_domain
        return EntryRoutingBackend(
            tag=tag,
            node_name=node.name,
            backend_node_id=node.id,
            server=server,
            server_port=self.config.backend_port,
            uuid=uuid,
            flow=self.config.backend_flow,
            reality_public_key=self.config.backend_reality_public_key,
            reality_short_id=self.config.reality_short_id,
            reality_server_name=self.config.reality_server_name,
            reality_fingerprint=self.config.backend_reality_fingerprint,
        )

    @staticmethod
    def _user_urltest_tag(client_id: str) -> str:
        return f"auto-{client_id}"

    def _materialize_outbounds_and_rules(
        self,
        users: list[EntryRoutingUser],
        backend_nodes: list[VpnNode],
        overrides: dict[str, str] | None = None,
    ) -> tuple[
        list[EntryRoutingBackend],
        list[EntryRoutingRule],
        list[EntryRoutingUrltestGroup],
        str,
    ]:
        if not backend_nodes:
            return [], [], [], "direct"
        sorted_nodes = sorted(backend_nodes, key=lambda n: n.name)
        node_by_backend_tag = {self._backend_node_tag(n): n for n in sorted_nodes}
        overrides = overrides or {}

        per_user_mode = self.config.backend_use_wg and self.config.per_user_outbound_uuid

        outbounds: list[EntryRoutingBackend] = []
        rules: list[EntryRoutingRule] = []
        urltest_groups: list[EntryRoutingUrltestGroup] = []
        seen_outbound_tags: set[str] = set()

        if not per_user_mode:
            for user in users:
                forced = overrides.get(user.uuid)
                if forced and forced in node_by_backend_tag:
                    assigned = node_by_backend_tag[forced]
                else:
                    digest = hashlib.sha256(user.uuid.encode()).digest()
                    idx = int.from_bytes(digest[:8], "big") % len(sorted_nodes)
                    assigned = sorted_nodes[idx]
                ob_tag = self._backend_node_tag(assigned)
                if ob_tag not in seen_outbound_tags:
                    outbounds.append(self._make_outbound(
                        assigned, tag=ob_tag, uuid=self.config.backend_service_uuid,
                    ))
                    seen_outbound_tags.add(ob_tag)
                rules.append(EntryRoutingRule(user_uuid=user.uuid, outbound_tag=ob_tag))
            return outbounds, rules, urltest_groups, self._backend_node_tag(sorted_nodes[0])

        for user in users:
            forced_tag = overrides.get(user.uuid)
            forced_node = node_by_backend_tag.get(forced_tag) if forced_tag else None

            if forced_node is not None:
                ob_tag = self._user_outbound_tag(forced_node.name, user.uuid)
                if ob_tag not in seen_outbound_tags:
                    outbounds.append(self._make_outbound(forced_node, tag=ob_tag, uuid=user.uuid))
                    seen_outbound_tags.add(ob_tag)
                rules.append(EntryRoutingRule(user_uuid=user.uuid, outbound_tag=ob_tag))
                continue

            per_user_outbound_tags: list[str] = []
            for node in sorted_nodes:
                ob_tag = self._user_outbound_tag(node.name, user.uuid)
                if ob_tag not in seen_outbound_tags:
                    outbounds.append(self._make_outbound(node, tag=ob_tag, uuid=user.uuid))
                    seen_outbound_tags.add(ob_tag)
                per_user_outbound_tags.append(ob_tag)

            if len(per_user_outbound_tags) == 1:
                rules.append(EntryRoutingRule(
                    user_uuid=user.uuid, outbound_tag=per_user_outbound_tags[0],
                ))
            else:
                urltest_tag = self._user_urltest_tag(user.uuid)
                urltest_groups.append(EntryRoutingUrltestGroup(
                    tag=urltest_tag,
                    outbounds=per_user_outbound_tags,
                ))
                rules.append(EntryRoutingRule(user_uuid=user.uuid, outbound_tag=urltest_tag))

        return outbounds, rules, urltest_groups, "block"


class EntryRoutingAdminService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        config: EntryRoutingConfig,
        nats_client: NatsClient | None = None,
    ):
        self.session = session
        self.config = config
        self.routing = EntryRoutingService(session, config=config)
        self.key_repo = self.routing.key_repo
        self._nats = nats_client

    async def get_state(self, *, key_limit: int = 500) -> RoutingStateOut:
        target_nodes = await self.routing.list_target_nodes()
        backends_by_tag: dict[str, RoutingBackendOut] = {}
        for entry in target_nodes:
            for b in await self.routing._build_backends_for_zone(entry):
                if b.tag not in backends_by_tag:
                    backends_by_tag[b.tag] = RoutingBackendOut(
                        tag=b.tag, server=b.server, server_port=b.server_port,
                    )
        backend_tags_sorted = sorted(backends_by_tag.keys())
        valid_tags = set(backend_tags_sorted)
        rows = await self.key_repo.list_active_with_user(limit=key_limit)
        keys = [
            RoutingKeyRowOut(
                key_id=row.id,
                client_id=row.client_id,
                user_id=row.user_id,
                user_username=getattr(row.user, "username", None) if row.user else None,
                user_telegram_id=getattr(row.user, "telegram_id", None) if row.user else None,
                subscription_id=row.subscription_id,
                transport=row.transport,
                is_revoked=row.is_revoked,
                override=row.entry_routing_override_backend_tag,
                effective_backend=self._effective_backend(
                    client_id=row.client_id,
                    override=row.entry_routing_override_backend_tag,
                    backend_tags_sorted=backend_tags_sorted,
                    valid_tags=valid_tags,
                ),
            )
            for row in rows
        ]
        live, live_by_entry = await self._collect_live_stats()
        return RoutingStateOut(
            backends=sorted(backends_by_tag.values(), key=lambda x: x.tag),
            keys=keys,
            live=live,
            live_by_entry=live_by_entry,
        )

    async def _collect_live_stats(
            self,
    ) -> tuple[list[RoutingLiveStatsByBackend], list[RoutingLiveStatsByEntry]]:
        if self._nats is None:
            return [], []
        try:
            entries = await self._nats.kv_list_all(bucket=KV_STATS_BUCKET)
        except Exception:
            logger.exception("entry_routing_live_stats_fetch_failed")
            return [], []
        by_backend_totals: dict[str, int] = {}
        by_entry_totals: dict[str, int] = {}
        by_entry_unique_users: dict[str, int] = {}
        for raw in entries.values():
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            for tag, count in (payload.get("by_backend") or {}).items():
                by_backend_totals[tag] = by_backend_totals.get(tag, 0) + int(count)
            node_id = payload.get("node_id")
            total = payload.get("total")
            if node_id and total is not None:
                by_entry_totals[str(node_id)] = by_entry_totals.get(str(node_id), 0) + int(total)
                by_entry_unique_users[str(node_id)] = (
                    by_entry_unique_users.get(str(node_id), 0) + int(payload.get("unique_users") or 0)
                )
        return (
            [
                RoutingLiveStatsByBackend(tag=tag, connections=count)
                for tag, count in sorted(by_backend_totals.items())
            ],
            [
                RoutingLiveStatsByEntry(
                    entry_node_id=node_id,
                    connections=count,
                    unique_users=by_entry_unique_users.get(node_id, 0),
                )
                for node_id, count in sorted(by_entry_totals.items())
            ],
        )

    async def get_live_entry_loads(self) -> dict[str, int]:
        """Return {entry_node_id: total_connections} from latest sing-box reports
        — used by the subscription selector for load-aware entry pick."""
        _, by_entry = await self._collect_live_stats()
        return {row.entry_node_id: row.connections for row in by_entry}

    @staticmethod
    def _effective_backend(
        *,
        client_id: str,
        override: str | None,
        backend_tags_sorted: list[str],
        valid_tags: set[str],
    ) -> str | None:
        if not backend_tags_sorted or not client_id:
            return None
        if override and override in valid_tags:
            return override
        digest = hashlib.sha256(client_id.encode()).digest()
        idx = int.from_bytes(digest[:8], "big") % len(backend_tags_sorted)
        return backend_tags_sorted[idx]

    async def set_key_override(
        self,
        *,
        key_id: UUID,
        backend_tag: str | None,
    ) -> OverrideChange | None:
        key = await self.key_repo.get_by_id(key_id)
        if key is None:
            return None
        normalized = (backend_tag or "").strip() or None
        if normalized is not None:
            valid_tags = await self._collect_valid_backend_tags()
            if normalized not in valid_tags:
                raise UnknownBackendTagError(normalized, sorted(valid_tags))
        previous = key.entry_routing_override_backend_tag
        changed = normalized != previous
        if changed:
            await self.key_repo.update_by_id(
                key_id, {"entry_routing_override_backend_tag": normalized},
            )
            key.entry_routing_override_backend_tag = normalized
        return OverrideChange(
            changed=changed,
            previous=previous,
            current=normalized,
            key=KeyRoutingOverrideOut(
                key_id=key.id,
                client_id=key.client_id,
                entry_routing_override_backend_tag=key.entry_routing_override_backend_tag,
            ),
        )

    async def _collect_valid_backend_tags(self) -> set[str]:
        target_nodes = await self.routing.list_target_nodes()
        tags: set[str] = set()
        for entry in target_nodes:
            for b in await self.routing._build_backends_for_zone(entry):
                tags.add(b.tag)
        return tags


def get_entry_routing_admin_service(
    request: Request,
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> EntryRoutingAdminService:
    nats_client = getattr(request.app.state, "nats_client", None)
    return EntryRoutingAdminService(
        session,
        config=get_settings().entry_routing,
        nats_client=nats_client,
    )
