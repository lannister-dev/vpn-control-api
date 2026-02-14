from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode, NodeAgentState
from services.vpn.keys.models import KeyAssignment


class RoutingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_available_nodes(
        self,
        preferred_region: str | None = None,
        exclude_node_ids: list[UUID] | None = None,
    ) -> list[tuple[VpnNode, NodeAgentState | None, int]]:
        """
        Returns available nodes with their agent state and active assignment count.

        Filters: is_active=True, is_enabled=True, is_draining=False.
        """
        active_assignments = (
            select(
                KeyAssignment.node_id,
                func.count(KeyAssignment.id).label("active_count"),
            )
            .where(
                KeyAssignment.is_active.is_(True),
                KeyAssignment.desired_state == "present",
                KeyAssignment.status.in_(["pending", "applied"]),
            )
            .group_by(KeyAssignment.node_id)
            .subquery()
        )

        stmt = (
            select(
                VpnNode,
                NodeAgentState,
                func.coalesce(active_assignments.c.active_count, 0).label("active_count"),
            )
            .outerjoin(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .outerjoin(active_assignments, active_assignments.c.node_id == VpnNode.id)
            .where(
                VpnNode.is_active.is_(True),
                VpnNode.is_enabled.is_(True),
                VpnNode.is_draining.is_(False),
            )
        )

        if exclude_node_ids:
            stmt = stmt.where(VpnNode.id.notin_(exclude_node_ids))

        if preferred_region:
            stmt = stmt.order_by(
                (VpnNode.region == preferred_region).desc(),
            )

        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]
