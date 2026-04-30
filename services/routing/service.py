from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import NodeAgentState, VpnNode
from services.routing.constants import ROUTING_TRAFFIC_WINDOW_SEC
from services.routing.repository import RoutingRepository
from shared.database.session import AsyncDatabase


class RoutingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = RoutingRepository(session)
        self._policy_cache = None
        self.node_state_stale_after_sec = 90

    async def _load_policy(self) -> None:
        if self._policy_cache is None:
            from services.nodes.policy.repository import NodePolicyRepository
            self._policy_cache = (await NodePolicyRepository(self.session).list(limit=1))[0]
        self.node_state_stale_after_sec = max(30, int(self._policy_cache.stale_after_sec))

    async def select_nodes(
        self,
        preferred_region: str | None = None,
        exclude_node_ids: list[UUID] | None = None,
    ) -> list[VpnNode]:
        await self._load_policy()
        rows = await self.repository.list_available_nodes(
            preferred_region=preferred_region,
            exclude_node_ids=exclude_node_ids,
        )
        traffic_by_node = await self.repository.recent_traffic_bytes_per_backend(
            window_sec=ROUTING_TRAFFIC_WINDOW_SEC,
        )
        max_recent_bytes = max(traffic_by_node.values(), default=0)

        scored: list[tuple[float, VpnNode]] = []
        now = datetime.now(timezone.utc)
        for node, agent_state, active_count in rows:
            if not self._is_healthy(agent_state, now=now):
                continue
            if active_count >= node.capacity:
                continue

            score = self._calc_score(
                node=node,
                agent_state=agent_state,
                active_count=active_count,
                recent_bytes=traffic_by_node.get(node.id, 0),
                max_recent_bytes=max_recent_bytes,
                preferred_region=preferred_region,
            )
            scored.append((score, node))

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
        recent_bytes: int,
        max_recent_bytes: int,
        preferred_region: str | None,
    ) -> float:
        count_ratio = active_count / node.capacity if node.capacity > 0 else 1.0
        traffic_ratio = recent_bytes / max_recent_bytes if max_recent_bytes > 0 else 0.0
        load_ratio = min(1.0, max(count_ratio, traffic_ratio))
        load_weight = 1.0 - load_ratio
        health_weight = 1.0 if agent_state and agent_state.is_healthy else 0.0
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
