from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.nodes.models import VpnNode, NodeAgentState
from services.routing.repository import RoutingRepository
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

logger_routing = StructuredLogger(logging.getLogger("routing-select"))


class RoutingService:
    def __init__(self, session: AsyncSession):
        self.repository = RoutingRepository(session)
        self.node_state_stale_after_sec = max(30, int(get_settings().node_agent.stale_after_sec))

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
        3. Filter: capacity > current active placements count
        4. If preferred_region — nodes of that region first
        5. Score: health_weight + load_weight (by capacity fill %)
        6. Sort by score DESC
        """
        rows = await self.repository.list_available_nodes(
            preferred_region=preferred_region,
            exclude_node_ids=exclude_node_ids,
        )
        logger_routing.info(
            "select_nodes_query_result",
            preferred_region=preferred_region,
            rows_from_db=len(rows),
            stale_after_sec=self.node_state_stale_after_sec,
        )
        scored: list[tuple[float, VpnNode]] = []
        now = datetime.now(timezone.utc)
        for node, agent_state, active_count in rows:
            is_healthy = self._is_healthy(agent_state, now=now)
            capacity_ok = active_count < node.capacity
            if not is_healthy or not capacity_ok:
                last_seen = self._to_utc_or_none(agent_state.last_seen_at) if agent_state else None
                staleness = (now - last_seen).total_seconds() if last_seen else None
                logger_routing.info(
                    "select_nodes_filtered_out",
                    node_id=str(node.id),
                    node_name=str(node.name),
                    is_healthy=is_healthy,
                    capacity_ok=capacity_ok,
                    active_count=active_count,
                    capacity=node.capacity,
                    agent_is_healthy=agent_state.is_healthy if agent_state else None,
                    last_seen_at=str(last_seen) if last_seen else None,
                    staleness_sec=staleness,
                )
                continue

            score = self._calc_score(
                node=node,
                agent_state=agent_state,
                active_count=active_count,
                preferred_region=preferred_region,
            )
            scored.append((score, node))

        logger_routing.info(
            "select_nodes_result",
            scored_count=len(scored),
            nodes=[str(n.name) for _, n in scored],
        )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in scored]

    def _is_healthy(self, agent_state: NodeAgentState | None, *, now: datetime) -> bool:
        if agent_state is None:
            return False
        if not agent_state.is_healthy:
            return False
        last_seen = self._to_utc_or_none(agent_state.last_seen_at)
        if last_seen is None:
            return False
        return (now - last_seen).total_seconds() <= self.node_state_stale_after_sec

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

    @staticmethod
    def _to_utc_or_none(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def get_routing_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> RoutingService:
    return RoutingService(session)
