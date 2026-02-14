from __future__ import annotations

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode, NodeAgentState
from services.routing.repository import RoutingRepository
from shared.database.session import AsyncDatabase


class RoutingService:
    def __init__(self, session: AsyncSession):
        self.repository = RoutingRepository(session)

    async def select_nodes(
        self,
        preferred_region: str | None = None,
        exclude_node_ids: list[UUID] | None = None,
    ) -> list[VpnNode]:
        """
        Returns sorted list of available nodes.

        Algorithm:
        1. Filter: is_active=True, is_enabled=True, is_draining=False
        2. Filter: is_healthy=True (via NodeAgentState)
        3. Filter: capacity > current active assignments count
        4. If preferred_region — nodes of that region first
        5. Score: health_weight + load_weight (by capacity fill %)
        6. Sort by score DESC
        """
        rows = await self.repository.list_available_nodes(
            preferred_region=preferred_region,
            exclude_node_ids=exclude_node_ids,
        )

        scored: list[tuple[float, VpnNode]] = []
        for node, agent_state, active_count in rows:
            if not self._is_healthy(agent_state):
                continue
            if active_count >= node.capacity:
                continue

            score = self._calc_score(
                node=node,
                agent_state=agent_state,
                active_count=active_count,
                preferred_region=preferred_region,
            )
            scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in scored]

    @staticmethod
    def _is_healthy(agent_state: NodeAgentState | None) -> bool:
        if agent_state is None:
            return False
        return agent_state.is_healthy

    @staticmethod
    def _calc_score(
        *,
        node: VpnNode,
        agent_state: NodeAgentState | None,
        active_count: int,
        preferred_region: str | None,
    ) -> float:
        # Load weight: 0.0 (full) to 1.0 (empty)
        load_ratio = active_count / node.capacity if node.capacity > 0 else 1.0
        load_weight = 1.0 - load_ratio

        # Health weight: healthy = 1.0
        health_weight = 1.0 if agent_state and agent_state.is_healthy else 0.0

        # Region bonus
        region_weight = 0.5 if preferred_region and node.region == preferred_region else 0.0

        return health_weight + load_weight + region_weight


def get_routing_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> RoutingService:
    return RoutingService(session)
