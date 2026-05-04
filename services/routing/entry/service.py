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
        backends = await self._build_backends_for_zone(node)
        rules, final_outbound = self._assign_users_to_backends(users, backends)
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
    ) -> tuple[list[EntryRoutingRule], str]:
        if not backends:
            return [], "direct"
        ordered = sorted(backends, key=lambda b: b.tag)
        rules: list[EntryRoutingRule] = []
        for user in users:
            digest = hashlib.sha256(user.uuid.encode()).digest()
            idx = int.from_bytes(digest[:8], "big") % len(ordered)
            rules.append(
                EntryRoutingRule(user_uuid=user.uuid, outbound_tag=ordered[idx].tag)
            )
        return rules, ordered[0].tag
