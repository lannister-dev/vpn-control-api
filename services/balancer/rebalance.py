from __future__ import annotations

import logging
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from services.balancer.backend import BackendBalancer
from services.nodes.repository import VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.vpn.keys.repository import VpnKeyRepository
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("balancer.rebalance"))


class BackendRebalancer:
    def __init__(self, session: AsyncSession, *, nats=None) -> None:
        self._nats = nats
        self._node_repository = VpnNodeRepository(session)
        self._key_repository = VpnKeyRepository(session)
        self._placement_repository = UserPlacementRepository(session)
        self._backend = BackendBalancer(nats=nats, vpn_key_repository=self._key_repository)

    async def rebalance(self) -> int:
        backends = await self._node_repository.list_live_backends()
        if len(backends) < 2:
            return 0
        nodes_by_id = {b.id: b for b in backends}

        keys = await self._key_repository.list_all_active()
        if not keys:
            return 0

        eligible = await self._placement_repository.map_active_backend_nodes_by_key(
            key_ids=[k.id for k in keys],
        )

        loads = await BackendBalancer.fetch_backend_loads(self._nats)
        if not loads:
            loads = Counter(
                k.entry_routing_override_backend_tag
                for k in keys
                if k.entry_routing_override_backend_tag
            )

        moved = 0
        for k in keys:
            allowed = [bid for bid in eligible.get(k.id, set()) if bid in nodes_by_id]
            if not allowed:
                continue
            before = k.entry_routing_override_backend_tag
            chosen = await self._backend.assign_key_backend(
                key_id=k.id,
                allowed_backend_ids=allowed,
                nodes_by_id=nodes_by_id,
                backend_loads=loads,
            )
            if chosen is not None and chosen != before:
                moved += 1

        if moved:
            logger.info("backend_rebalance_applied", moved=moved, backends=len(backends))
        return moved
