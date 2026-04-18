from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.constants import ROLE_BACKEND
from services.nodes.repository import VpnNodeRepository
from services.traffic.nodes.repository import NodeTrafficUsageRepository
from services.traffic.nodes.schemas import (
    NodePairListOut,
    NodePairTrafficOut,
    NodeTimeseriesOut,
    NodeTrafficCreate,
    NodeTrafficIn,
    NodeTrafficSummaryListOut,
    NodeTrafficSummaryOut,
    TrafficPeriod,
)
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("node-traffic-service"))


_PERIOD_WINDOW: dict[TrafficPeriod, tuple[timedelta, int]] = {
    TrafficPeriod.HOUR: (timedelta(hours=1), 60),
    TrafficPeriod.DAY: (timedelta(days=1), 300),
    TrafficPeriod.WEEK: (timedelta(days=7), 3600),
    TrafficPeriod.MONTH: (timedelta(days=30), 6 * 3600),
}


def _window(period: TrafficPeriod, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    length, _ = _PERIOD_WINDOW[period]
    return now - length, now


def _resolution_seconds(period: TrafficPeriod) -> int:
    return _PERIOD_WINDOW[period][1]


class NodeTrafficService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.node_repo = VpnNodeRepository(session)
        self.usage_repo = NodeTrafficUsageRepository(session)

    async def ingest(self, items: list[NodeTrafficIn]) -> int:
        if not items:
            return 0
        rows = [
            NodeTrafficCreate(**item.model_dump())
            for item in items
        ]
        return await self.usage_repo.bulk_create(rows)

    async def list_nodes_summary(
        self,
        *,
        period: TrafficPeriod,
        role: str | None = None,
    ) -> NodeTrafficSummaryListOut:
        from_ts, to_ts = _window(period)
        nodes = await self.node_repo.list()
        if role:
            nodes = [n for n in nodes if n.role == role]

        entry_aggs = await self.usage_repo.sum_by_entry(from_ts=from_ts, to_ts=to_ts)
        backend_aggs = await self.usage_repo.sum_by_backend(from_ts=from_ts, to_ts=to_ts)
        entry_map = {a.node_id: a for a in entry_aggs}
        backend_map = {a.node_id: a for a in backend_aggs}

        items: list[NodeTrafficSummaryOut] = []
        for node in nodes:
            e = entry_map.get(node.id)
            b = backend_map.get(node.id)
            bytes_in = (e.bytes_in if e else 0) + (b.bytes_in if b else 0)
            bytes_out = (e.bytes_out if e else 0) + (b.bytes_out if b else 0)
            total_sessions = (e.total_sessions if e else 0) + (b.total_sessions if b else 0)
            active_sessions = max(
                e.active_sessions if e else 0,
                b.active_sessions if b else 0,
            )
            items.append(
                NodeTrafficSummaryOut(
                    node_id=node.id,
                    role=node.role,
                    name=node.name,
                    region=node.region,
                    is_enabled=node.is_enabled,
                    is_draining=node.is_draining,
                    bytes_in=bytes_in,
                    bytes_out=bytes_out,
                    total_bytes=bytes_in + bytes_out,
                    total_sessions=total_sessions,
                    active_sessions=active_sessions,
                )
            )
        items.sort(key=lambda x: x.total_bytes, reverse=True)
        return NodeTrafficSummaryListOut(
            period=period,
            from_ts=from_ts,
            to_ts=to_ts,
            items=items,
        )

    async def node_timeseries(
        self,
        *,
        node_id: UUID,
        period: TrafficPeriod,
        side: str = "auto",
        resolution_seconds: int | None = None,
    ) -> NodeTimeseriesOut:
        if side == "auto":
            node = await self.node_repo.get_by_id(node_id)
            side = "backend" if (node is not None and node.role == ROLE_BACKEND) else "entry"

        resolution = resolution_seconds or _resolution_seconds(period)
        from_ts, to_ts = _window(period)
        points = await self.usage_repo.timeseries_for_node(
            node_id=node_id,
            from_ts=from_ts,
            to_ts=to_ts,
            resolution_seconds=resolution,
            side=side,
        )
        return NodeTimeseriesOut(
            node_id=node_id,
            period=period,
            from_ts=from_ts,
            to_ts=to_ts,
            resolution_seconds=resolution,
            points=points,
        )

    async def pair_matrix(self, *, period: TrafficPeriod) -> NodePairListOut:
        from_ts, to_ts = _window(period)
        pair_rows = await self.usage_repo.pair_totals(from_ts=from_ts, to_ts=to_ts)

        referenced: set[UUID] = set()
        for row in pair_rows:
            referenced.add(row.entry_node_id)
            if row.backend_node_id is not None:
                referenced.add(row.backend_node_id)
        nodes = await self.node_repo.list_by_ids(list(referenced))
        by_id = {n.id: n for n in nodes}

        items: list[NodePairTrafficOut] = []
        for row in pair_rows:
            entry = by_id.get(row.entry_node_id)
            backend = by_id.get(row.backend_node_id) if row.backend_node_id else None
            items.append(
                NodePairTrafficOut(
                    entry_node_id=row.entry_node_id,
                    entry_name=entry.name if entry else str(row.entry_node_id),
                    backend_node_id=row.backend_node_id,
                    backend_name=backend.name if backend else None,
                    bytes_in=row.bytes_in,
                    bytes_out=row.bytes_out,
                    total_bytes=row.bytes_in + row.bytes_out,
                    total_sessions=row.total_sessions,
                )
            )
        return NodePairListOut(
            period=period,
            from_ts=from_ts,
            to_ts=to_ts,
            items=items,
        )


async def get_node_traffic_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> NodeTrafficService:
    return NodeTrafficService(session)
