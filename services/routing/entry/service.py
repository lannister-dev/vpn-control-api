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
    EntryRoutingUser,
    KeyRoutingOverrideOut,
    OverrideChange,
    RoutingBackendOut,
    RoutingKeyRowOut,
    RoutingLiveStatsByBackend,
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
        backends = await self._build_backends_for_zone(node)
        rules, final_outbound = self._assign_users_to_backends(users, backends, overrides)
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
            final_outbound=final_outbound,
        )

    async def _build_backends_for_zone(self, entry: VpnNode) -> list[EntryRoutingBackend]:
        if not self.config.backend_service_uuid:
            return []
        if self.config.backend_use_wg:
            if not self._has_wg_addr(entry):
                return []
        elif not self.config.backend_reality_public_key:
            return []
        zone = effective_zone(explicit_zone=entry.zone, region=entry.region)
        all_nodes = await self.node_repo.list()
        candidates = [
            n for n in all_nodes
            if n.role == ROLE_BACKEND
            and n.is_enabled
            and not n.is_draining
            and effective_zone(explicit_zone=n.zone, region=n.region) == zone
            and self._has_reachable_addr(n)
        ]
        return [self._backend_to_outbound(n) for n in candidates]

    def _has_reachable_addr(self, node: VpnNode) -> bool:
        if self.config.backend_use_wg:
            return self._has_wg_addr(node)
        return bool(node.reality_ip or node.public_domain)

    @staticmethod
    def _has_wg_addr(node: VpnNode) -> bool:
        ip = (node.internal_wg_ip or "").strip()
        return bool(ip) and not ip.startswith("0.")

    def _backend_to_outbound(self, node: VpnNode) -> EntryRoutingBackend:
        if self.config.backend_use_wg:
            return EntryRoutingBackend(
                tag=f"backend-{node.name}",
                backend_node_id=node.id,
                server=node.internal_wg_ip,
                server_port=self.config.backend_wg_port,
                uuid=self.config.backend_service_uuid,
                flow="",
            )
        server = node.reality_ip or node.public_domain
        return EntryRoutingBackend(
            tag=f"backend-{node.name}",
            backend_node_id=node.id,
            server=server,
            server_port=self.config.backend_port,
            uuid=self.config.backend_service_uuid,
            flow=self.config.backend_flow,
            reality_public_key=self.config.backend_reality_public_key,
            reality_short_id=self.config.reality_short_id,
            reality_server_name=self.config.reality_server_name,
            reality_fingerprint=self.config.backend_reality_fingerprint,
        )

    @staticmethod
    def _assign_users_to_backends(
        users: list[EntryRoutingUser],
        backends: list[EntryRoutingBackend],
        overrides: dict[str, str] | None = None,
    ) -> tuple[list[EntryRoutingRule], str]:
        if not backends:
            return [], "direct"
        ordered = sorted(backends, key=lambda b: b.tag)
        valid_tags = {b.tag for b in ordered}
        overrides = overrides or {}
        rules: list[EntryRoutingRule] = []
        for user in users:
            forced = overrides.get(user.uuid)
            if forced and forced in valid_tags:
                rules.append(
                    EntryRoutingRule(user_uuid=user.uuid, outbound_tag=forced)
                )
                continue
            digest = hashlib.sha256(user.uuid.encode()).digest()
            idx = int.from_bytes(digest[:8], "big") % len(ordered)
            rules.append(
                EntryRoutingRule(user_uuid=user.uuid, outbound_tag=ordered[idx].tag)
            )
        return rules, ordered[0].tag


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
        live = await self._collect_live_stats()
        return RoutingStateOut(
            backends=sorted(backends_by_tag.values(), key=lambda x: x.tag),
            keys=keys,
            live=live,
        )

    async def _collect_live_stats(self) -> list[RoutingLiveStatsByBackend]:
        if self._nats is None:
            return []
        try:
            entries = await self._nats.kv_list_all(bucket=KV_STATS_BUCKET)
        except Exception:
            logger.exception("entry_routing_live_stats_fetch_failed")
            return []
        totals: dict[str, int] = {}
        for raw in entries.values():
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            for tag, count in (payload.get("by_backend") or {}).items():
                totals[tag] = totals.get(tag, 0) + int(count)
        return [
            RoutingLiveStatsByBackend(tag=tag, connections=count)
            for tag, count in sorted(totals.items())
        ]

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
