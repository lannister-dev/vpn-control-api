from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.constants import ROLE_BACKEND
from services.nodes.repository import VpnNodeRepository
from services.traffic.nodes.constants import PERIOD_WINDOW
from services.traffic.nodes.repository import NodeTrafficUsageRepository
from services.traffic.nodes.schemas import (
    FleetTimeseriesBucket,
    FleetTimeseriesOut,
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


def _window(period: TrafficPeriod, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    length, _ = PERIOD_WINDOW[period]
    return now - length, now


def _resolution_seconds(period: TrafficPeriod) -> int:
    return PERIOD_WINDOW[period][1]


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

        entry_aggs = await self.usage_repo.sum_entry_self(from_ts=from_ts, to_ts=to_ts)
        backend_aggs = await self.usage_repo.sum_backend_self(from_ts=from_ts, to_ts=to_ts)
        entry_map = {a.node_id: a for a in entry_aggs}
        backend_map = {a.node_id: a for a in backend_aggs}

        items: list[NodeTrafficSummaryOut] = []
        for node in nodes:
            source = backend_map.get(node.id) if node.role == ROLE_BACKEND else entry_map.get(node.id)
            bytes_in = source.bytes_in if source else 0
            bytes_out = source.bytes_out if source else 0
            total_sessions = source.total_sessions if source else 0
            active_sessions = source.active_sessions if source else 0
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

    async def fleet_timeseries(
        self,
        *,
        period: TrafficPeriod,
        resolution_seconds: int | None = None,
    ) -> FleetTimeseriesOut:
        resolution = resolution_seconds or _resolution_seconds(period)
        from_ts, to_ts = _window(period)
        rows = await self.usage_repo.fleet_timeseries_by_region(
            from_ts=from_ts,
            to_ts=to_ts,
            resolution_seconds=resolution,
        )
        by_bucket: dict = {}
        regions_set: set[str] = set()
        for ts, region, bin_, bout in rows:
            regions_set.add(region)
            b = by_bucket.setdefault(ts, {"in": 0, "out": 0, "by_region": {}})
            b["in"] += bin_
            b["out"] += bout
            b["by_region"][region] = b["by_region"].get(region, 0) + bin_ + bout
        regions = sorted(regions_set)
        points = [
            FleetTimeseriesBucket(
                ts=ts,
                bytes_in=v["in"],
                bytes_out=v["out"],
                by_region={r: v["by_region"].get(r, 0) for r in regions},
            )
            for ts, v in sorted(by_bucket.items(), key=lambda kv: kv[0])
        ]
        return FleetTimeseriesOut(
            period=period,
            from_ts=from_ts,
            to_ts=to_ts,
            resolution_seconds=resolution,
            regions=regions,
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
