from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode
from services.traffic.nodes.model import NodeTrafficUsage
from services.traffic.nodes.schemas import (
    NodePairAggregate,
    NodeTimeseriesBucket,
    NodeTrafficAggregate,
    NodeTrafficCreate,
)
from shared.database.base_repository import BaseRepository


class NodeTrafficUsageRepository(BaseRepository[NodeTrafficUsage]):
    def __init__(self, session: AsyncSession):
        super().__init__(NodeTrafficUsage, session)

    async def bulk_create(self, rows: list[NodeTrafficCreate]) -> int:
        if not rows:
            return 0
        objects = [self.model(**row.model_dump()) for row in rows]
        self.session.add_all(objects)
        await self.session.flush()
        return len(objects)

    async def sum_entry_self(
        self,
        *,
        from_ts: datetime,
        to_ts: datetime,
    ) -> list[NodeTrafficAggregate]:
        stmt = (
            select(
                self.model.entry_node_id,
                func.coalesce(func.sum(self.model.bytes_in), 0),
                func.coalesce(func.sum(self.model.bytes_out), 0),
                func.coalesce(func.sum(self.model.total_sessions), 0),
                func.coalesce(func.max(self.model.active_sessions), 0),
            )
            .where(self.model.created_at >= from_ts)
            .where(self.model.created_at < to_ts)
            .where(self.model.entry_node_id.is_not(None))
            .group_by(self.model.entry_node_id)
        )
        result = await self.session.execute(stmt)
        return [
            NodeTrafficAggregate(
                node_id=row[0],
                bytes_in=int(row[1]),
                bytes_out=int(row[2]),
                total_sessions=int(row[3]),
                active_sessions=int(row[4]),
            )
            for row in result.all()
        ]

    async def sum_backend_self(
        self,
        *,
        from_ts: datetime,
        to_ts: datetime,
    ) -> list[NodeTrafficAggregate]:
        stmt = (
            select(
                self.model.backend_node_id,
                func.coalesce(func.sum(self.model.bytes_in), 0),
                func.coalesce(func.sum(self.model.bytes_out), 0),
                func.coalesce(func.sum(self.model.total_sessions), 0),
                func.coalesce(func.max(self.model.active_sessions), 0),
            )
            .where(self.model.created_at >= from_ts)
            .where(self.model.created_at < to_ts)
            .where(self.model.entry_node_id.is_(None))
            .where(self.model.backend_node_id.is_not(None))
            .group_by(self.model.backend_node_id)
        )
        result = await self.session.execute(stmt)
        return [
            NodeTrafficAggregate(
                node_id=row[0],
                bytes_in=int(row[1]),
                bytes_out=int(row[2]),
                total_sessions=int(row[3]),
                active_sessions=int(row[4]),
            )
            for row in result.all()
        ]

    async def timeseries_for_node(
        self,
        *,
        node_id: UUID,
        from_ts: datetime,
        to_ts: datetime,
        resolution_seconds: int,
        side: str,
    ) -> list[NodeTimeseriesBucket]:
        if side not in ("entry", "backend"):
            raise ValueError(f"side must be 'entry' or 'backend', got {side!r}")

        epoch = func.extract("epoch", self.model.created_at)
        bucket_idx = cast(epoch / resolution_seconds, BigInteger)
        bucket_ts = func.to_timestamp(bucket_idx * resolution_seconds)

        stmt = (
            select(
                bucket_ts,
                func.coalesce(func.sum(self.model.bytes_in), 0),
                func.coalesce(func.sum(self.model.bytes_out), 0),
                func.coalesce(func.max(self.model.active_sessions), 0),
            )
            .where(self.model.created_at >= from_ts)
            .where(self.model.created_at < to_ts)
            .group_by(bucket_ts)
            .order_by(bucket_ts.asc())
        )
        if side == "entry":
            stmt = stmt.where(self.model.entry_node_id == node_id)
        else:
            stmt = stmt.where(self.model.backend_node_id == node_id)
            stmt = stmt.where(self.model.entry_node_id.is_(None))
        result = await self.session.execute(stmt)
        return [
            NodeTimeseriesBucket(
                ts=row[0],
                bytes_in=int(row[1]),
                bytes_out=int(row[2]),
                active_sessions=int(row[3]),
            )
            for row in result.all()
        ]

    async def pair_totals(
        self,
        *,
        from_ts: datetime,
        to_ts: datetime,
    ) -> list[NodePairAggregate]:
        stmt = (
            select(
                self.model.entry_node_id,
                self.model.backend_node_id,
                func.coalesce(func.sum(self.model.bytes_in), 0),
                func.coalesce(func.sum(self.model.bytes_out), 0),
                func.coalesce(func.sum(self.model.total_sessions), 0),
            )
            .where(self.model.created_at >= from_ts)
            .where(self.model.created_at < to_ts)
            .where(self.model.entry_node_id.is_not(None))
            .where(self.model.backend_node_id.is_not(None))
            .group_by(self.model.entry_node_id, self.model.backend_node_id)
            .order_by(func.sum(self.model.bytes_in + self.model.bytes_out).desc())
        )
        result = await self.session.execute(stmt)
        return [
            NodePairAggregate(
                entry_node_id=row[0],
                backend_node_id=row[1],
                bytes_in=int(row[2]),
                bytes_out=int(row[3]),
                total_sessions=int(row[4]),
            )
            for row in result.all()
        ]

    async def fleet_timeseries_by_region(
        self,
        *,
        from_ts: datetime,
        to_ts: datetime,
        resolution_seconds: int,
    ) -> list[tuple[datetime, str, int, int]]:
        epoch = func.extract("epoch", self.model.created_at)
        bucket_idx = cast(epoch / resolution_seconds, BigInteger)
        bucket_ts = func.to_timestamp(bucket_idx * resolution_seconds)
        self_node_id = func.coalesce(self.model.entry_node_id, self.model.backend_node_id)

        stmt = (
            select(
                bucket_ts.label("ts"),
                VpnNode.region.label("region"),
                func.coalesce(func.sum(self.model.bytes_in), 0),
                func.coalesce(func.sum(self.model.bytes_out), 0),
            )
            .join(VpnNode, VpnNode.id == self_node_id)
            .where(self.model.created_at >= from_ts)
            .where(self.model.created_at < to_ts)
            .group_by(bucket_ts, VpnNode.region)
            .order_by(bucket_ts.asc())
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1], int(row[2]), int(row[3])) for row in result.all()]

    async def delete_older_than(self, *, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(self.model).where(self.model.created_at < cutoff)
        )
        rowcount = result.rowcount
        if callable(rowcount):
            rowcount = rowcount()
        return int(rowcount or 0)
