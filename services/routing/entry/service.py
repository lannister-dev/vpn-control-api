from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.config import EntryRoutingConfig
from services.nodes.constants import ROLE_BACKEND, ROLE_ENTRY, ROLE_WHITELIST_ENTRY
from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
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
    RoutingStateOut,
)
from services.vpn.keys.repository import VpnKeyRepository
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
        if not (self.config.backend_service_uuid and self.config.backend_reality_public_key):
            return []
        zone = effective_zone(explicit_zone=entry.zone, region=entry.region)
        all_nodes = await self.node_repo.list()
        candidates = [
            n for n in all_nodes
            if n.role == ROLE_BACKEND
            and n.is_enabled
            and not n.is_draining
            and effective_zone(explicit_zone=n.zone, region=n.region) == zone
            and (n.reality_ip or n.public_domain)
        ]
        return [self._backend_to_outbound(n) for n in candidates]

    def _backend_to_outbound(self, node: VpnNode) -> EntryRoutingBackend:
        server = node.reality_ip or node.public_domain
        return EntryRoutingBackend(
            tag=f"backend-{node.name}",
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
    def __init__(self, session: AsyncSession, *, config: EntryRoutingConfig):
        self.session = session
        self.config = config
        self.routing = EntryRoutingService(session, config=config)
        self.key_repo = self.routing.key_repo

    async def get_state(self, *, key_limit: int = 500) -> RoutingStateOut:
        target_nodes = await self.routing.list_target_nodes()
        backends_by_tag: dict[str, RoutingBackendOut] = {}
        for entry in target_nodes:
            for b in await self.routing._build_backends_for_zone(entry):
                if b.tag not in backends_by_tag:
                    backends_by_tag[b.tag] = RoutingBackendOut(
                        tag=b.tag, server=b.server, server_port=b.server_port,
                    )
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
            )
            for row in rows
        ]
        return RoutingStateOut(
            backends=sorted(backends_by_tag.values(), key=lambda x: x.tag),
            keys=keys,
        )

    async def set_key_override(
        self,
        *,
        key_id: UUID,
        backend_tag: str | None,
    ) -> OverrideChange | None:
        key = await self.key_repo.get_by_id(key_id)
        if key is None:
            return None
        previous = key.entry_routing_override_backend_tag
        normalized = (backend_tag or "").strip() or None
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
