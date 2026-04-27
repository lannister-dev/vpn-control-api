from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import Depends
from sqlalchemy import delete, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from services.probe.model import ProbeSignal
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class ProbeSignalRepository(BaseRepository[ProbeSignal]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProbeSignal, session)

    async def get_latest_for_node(
            self,
            *,
            node_id: UUID,
            source: str | None = None,
    ) -> ProbeSignal | None:
        stmt = select(self.model).where(
            self.model.is_active.is_(True),
            self.model.node_id == node_id,
            self.model.route_id.is_(None),
        )
        if source:
            stmt = stmt.where(self.model.source == source)
        stmt = stmt.order_by(self.model.checked_at.desc(), self.model.created_at.desc()).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_for_route(
            self,
            *,
            route_id: UUID,
            source: str | None = None,
    ) -> ProbeSignal | None:
        stmt = select(self.model).where(
            self.model.is_active.is_(True),
            self.model.route_id == route_id,
        )
        if source:
            stmt = stmt.where(self.model.source == source)
        stmt = stmt.order_by(self.model.checked_at.desc(), self.model.created_at.desc()).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_recent(
            self,
            *,
            limit: int,
            node_id: UUID | None = None,
            route_id: UUID | None = None,
            source: str | None = None,
    ) -> list[ProbeSignal]:
        stmt = select(self.model).where(self.model.is_active.is_(True))
        if node_id is not None:
            stmt = stmt.where(self.model.node_id == node_id)
        if route_id is not None:
            stmt = stmt.where(self.model.route_id == route_id)
        if source:
            stmt = stmt.where(self.model.source == source)
        stmt = stmt.order_by(self.model.checked_at.desc(), self.model.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_recent_for_node(
            self,
            *,
            limit: int,
            node_id: UUID,
            source: str | None = None,
    ) -> list[ProbeSignal]:
        stmt = select(self.model).where(
            self.model.is_active.is_(True),
            self.model.node_id == node_id,
            self.model.route_id.is_(None),
        )
        if source:
            stmt = stmt.where(self.model.source == source)
        stmt = stmt.order_by(self.model.checked_at.desc(), self.model.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_latest_for_backend_node(
            self,
            *,
            node_id: UUID,
            source: str | None = None,
    ) -> ProbeSignal | None:
        stmt = select(self.model).where(
            self.model.is_active.is_(True),
            self.model.node_id == node_id,
            or_(
                self.model.route_id.is_(None),
                self.model.probe_kind == "synthetic_vpn",
            ),
        )
        if source:
            stmt = stmt.where(self.model.source == source)
        stmt = stmt.order_by(self.model.checked_at.desc(), self.model.created_at.desc()).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_recent_for_backend_node(
            self,
            *,
            limit: int,
            node_id: UUID,
            source: str | None = None,
    ) -> list[ProbeSignal]:
        stmt = select(self.model).where(
            self.model.is_active.is_(True),
            self.model.node_id == node_id,
            or_(
                self.model.route_id.is_(None),
                self.model.probe_kind == "synthetic_vpn",
            ),
        )
        if source:
            stmt = stmt.where(self.model.source == source)
        stmt = stmt.order_by(self.model.checked_at.desc(), self.model.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count_consecutive_route_failures(
            self,
            *,
            route_id: UUID,
            limit: int = 10,
    ) -> int:
        stmt = (
            select(self.model.is_reachable)
            .where(
                self.model.is_active.is_(True),
                self.model.route_id == route_id,
            )
            .order_by(self.model.checked_at.desc(), self.model.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        count = 0
        for (is_reachable,) in res.all():
            if is_reachable:
                break
            count += 1
        return count

    async def count_consecutive_node_failures(
            self,
            *,
            node_id: UUID,
            limit: int = 10,
    ) -> int:
        stmt = (
            select(self.model.is_reachable)
            .where(
                self.model.is_active.is_(True),
                self.model.node_id == node_id,
                self.model.route_id.is_(None),
            )
            .order_by(self.model.checked_at.desc(), self.model.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        count = 0
        for (is_reachable,) in res.all():
            if is_reachable:
                break
            count += 1
        return count

    async def delete_older_than(self, *, cutoff: datetime) -> int:
        stmt = delete(self.model).where(
            self.model.checked_at < cutoff,
        )
        result = cast(CursorResult, await self.session.execute(stmt))
        rowcount = result.rowcount
        if callable(rowcount):
            rowcount = rowcount()
        if rowcount is None or rowcount < 0:
            return 0
        return int(rowcount)


def get_probe_signal_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> ProbeSignalRepository:
    return ProbeSignalRepository(session)
