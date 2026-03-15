from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import NodeAgentState, VpnNode
from services.routes.model import Route, TransportProfile
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class TransportProfileRepository(BaseRepository[TransportProfile]):
    def __init__(self, session: AsyncSession):
        super().__init__(TransportProfile, session)

    async def list_active(self, *, limit: int | None = None) -> list[TransportProfile]:
        stmt = select(self.model).where(self.model.is_active.is_(True)).order_by(self.model.name.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_by_names(self, names: list[str]) -> list[TransportProfile]:
        if not names:
            return []
        stmt = select(self.model).where(self.model.name.in_(names))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class RouteRepository(BaseRepository[Route]):
    def __init__(self, session: AsyncSession):
        super().__init__(Route, session)

    async def list_active(
            self,
            *,
            node_id: UUID | None = None,
            limit: int | None = None,
    ) -> list[Route]:
        stmt = select(self.model).where(self.model.is_active.is_(True))
        if node_id is not None:
            stmt = stmt.where(self.model.node_id == node_id)
        stmt = stmt.order_by(self.model.effective_weight.desc(), self.model.name.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_active_detailed(
            self,
            *,
            node_id: UUID | None = None,
            limit: int | None = None,
    ) -> list[tuple[Route, VpnNode, TransportProfile, NodeAgentState | None]]:
        stmt = (
            select(Route, VpnNode, TransportProfile, NodeAgentState)
            .join(VpnNode, VpnNode.id == Route.node_id)
            .join(TransportProfile, TransportProfile.id == Route.transport_profile_id)
            .outerjoin(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .where(Route.is_active.is_(True))
            .order_by(Route.effective_weight.desc(), Route.name.asc())
        )
        if node_id is not None:
            stmt = stmt.where(Route.node_id == node_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        res = await self.session.execute(stmt)
        return list(res.tuples().all())

    async def list_by_names(self, names: list[str]) -> list[Route]:
        if not names:
            return []
        stmt = select(self.model).where(self.model.name.in_(names))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_warming_up(self) -> list[Route]:
        stmt = (
            select(self.model)
            .where(
                self.model.is_active.is_(True),
                self.model.health_status == "warming_up",
            )
            .order_by(self.model.updated_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_resolved_active(
            self,
            *,
            preferred_node_id: UUID | None,
            preferred_region: str | None,
            limit: int,
            node_seen_after: datetime | None = None,
    ) -> list[tuple[Route, VpnNode, TransportProfile]]:
        status_order = (
            case(
                (Route.health_status == "healthy", 0),
                (Route.health_status == "warming_up", 1),
                (Route.health_status == "degraded", 2),
                (Route.health_status == "suspected", 3),
                else_=4,
            )
        )
        stmt = (
            select(Route, VpnNode, TransportProfile)
            .join(VpnNode, VpnNode.id == Route.node_id)
            .join(TransportProfile, TransportProfile.id == Route.transport_profile_id)
            .join(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .where(
                Route.is_active.is_(True),
                Route.effective_weight > 0,
                Route.health_status.in_(("healthy", "warming_up", "degraded", "suspected")),
                TransportProfile.is_active.is_(True),
                VpnNode.is_active.is_(True),
                VpnNode.is_enabled.is_(True),
                VpnNode.is_draining.is_(False),
                VpnNode.role == "backend",
                NodeAgentState.is_healthy.is_(True),
            )
        )
        if node_seen_after is not None:
            stmt = stmt.where(NodeAgentState.last_seen_at >= node_seen_after)
        if preferred_node_id is not None:
            stmt = stmt.order_by(
                (Route.node_id == preferred_node_id).desc(),
                status_order.asc(),
                Route.effective_weight.desc(),
            )
        elif preferred_region:
            stmt = stmt.order_by(
                (VpnNode.region == preferred_region).desc(),
                status_order.asc(),
                Route.effective_weight.desc(),
            )
        else:
            stmt = stmt.order_by(
                status_order.asc(),
                Route.effective_weight.desc(),
            )
        stmt = stmt.limit(limit)
        res = await self.session.execute(stmt)
        return list(res.tuples().all())

    async def count_resolved_active(self, *, node_seen_after: datetime | None = None) -> int:
        stmt = (
            select(func.count(Route.id))
            .select_from(Route)
            .join(VpnNode, VpnNode.id == Route.node_id)
            .join(TransportProfile, TransportProfile.id == Route.transport_profile_id)
            .join(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .where(
                Route.is_active.is_(True),
                Route.effective_weight > 0,
                Route.health_status.in_(("healthy", "warming_up", "degraded", "suspected")),
                TransportProfile.is_active.is_(True),
                VpnNode.is_active.is_(True),
                VpnNode.is_enabled.is_(True),
                VpnNode.is_draining.is_(False),
                VpnNode.role == "backend",
                NodeAgentState.is_healthy.is_(True),
            )
        )
        if node_seen_after is not None:
            stmt = stmt.where(NodeAgentState.last_seen_at >= node_seen_after)
        res = await self.session.execute(stmt)
        return int(res.scalar_one() or 0)

    async def count_resolved_active_by_region(
            self,
            *,
            node_seen_after: datetime | None = None,
    ) -> dict[str, int]:
        stmt = (
            select(VpnNode.region, func.count(Route.id))
            .select_from(Route)
            .join(VpnNode, VpnNode.id == Route.node_id)
            .join(TransportProfile, TransportProfile.id == Route.transport_profile_id)
            .join(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .where(
                Route.is_active.is_(True),
                Route.effective_weight > 0,
                Route.health_status.in_(("healthy", "warming_up", "degraded", "suspected")),
                TransportProfile.is_active.is_(True),
                VpnNode.is_active.is_(True),
                VpnNode.is_enabled.is_(True),
                VpnNode.is_draining.is_(False),
                VpnNode.role == "backend",
                NodeAgentState.is_healthy.is_(True),
            )
            .group_by(VpnNode.region)
        )
        if node_seen_after is not None:
            stmt = stmt.where(NodeAgentState.last_seen_at >= node_seen_after)
        res = await self.session.execute(stmt)
        rows = res.all()
        return {str(region): int(total) for region, total in rows}


def get_transport_profile_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> TransportProfileRepository:
    return TransportProfileRepository(session)


def get_route_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> RouteRepository:
    return RouteRepository(session)
