from __future__ import annotations

import inspect
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode, NodeAgentState
from services.placements.model import UserPlacement


class RoutingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_available_nodes(
        self,
        preferred_region: str | None = None,
        exclude_node_ids: list[UUID] | None = None,
    ) -> list[tuple[VpnNode, NodeAgentState | None, int]]:
        """
        Returns available nodes with their agent state and active placement count.

        Filters: is_active=True, is_enabled=True, is_draining=False.
        """
        active_placements = (
            select(
                UserPlacement.backend_node_id.label("node_id"),
                func.count(UserPlacement.id).label("active_count"),
            )
            .where(
                UserPlacement.is_active.is_(True),
                UserPlacement.desired_state == "active",
            )
            .group_by(UserPlacement.backend_node_id)
            .subquery()
        )
        active_count_expr = func.coalesce(active_placements.c.active_count, 0)

        stmt = (
            select(
                VpnNode,
                NodeAgentState,
                active_count_expr.label("active_count"),
            )
            .join(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .outerjoin(active_placements, active_placements.c.node_id == VpnNode.id)
            .where(
                VpnNode.is_active.is_(True),
                VpnNode.is_enabled.is_(True),
                VpnNode.is_draining.is_(False),
                NodeAgentState.is_healthy.is_(True),
                VpnNode.capacity > 0,
                active_count_expr < VpnNode.capacity,
            )
        )
        if exclude_node_ids:
            stmt = stmt.where(VpnNode.id.notin_(exclude_node_ids))

        if preferred_region:
            stmt = stmt.order_by(
                (VpnNode.region == preferred_region).desc(),
            )

        result = await self.session.execute(stmt)
        rows = result.all()
        if inspect.isawaitable(rows):
            rows = await rows
        return [(row[0], row[1], row[2]) for row in rows]
