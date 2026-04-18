from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from services.auth.dependencies import admin_auth
from services.traffic.nodes.schemas import (
    NodePairListOut,
    NodeTimeseriesOut,
    NodeTrafficSummaryListOut,
    TrafficPeriod,
)
from services.traffic.nodes.service import NodeTrafficService, get_node_traffic_service

router = APIRouter(
    prefix="/admin/traffic/nodes",
    tags=["Admin Traffic · Nodes"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "",
    response_model=NodeTrafficSummaryListOut,
    status_code=status.HTTP_200_OK,
    summary="Per-node traffic totals for the selected period",
)
async def list_nodes_traffic(
    period: TrafficPeriod = Query(TrafficPeriod.DAY),
    role: str | None = Query(None, description="Filter by node role: entry, backend, whitelist_entry"),
    service: NodeTrafficService = Depends(get_node_traffic_service),
) -> NodeTrafficSummaryListOut:
    return await service.list_nodes_summary(period=period, role=role)


@router.get(
    "/{node_id}/timeseries",
    response_model=NodeTimeseriesOut,
    status_code=status.HTTP_200_OK,
    summary="Bucketed timeseries for a single node",
)
async def node_traffic_timeseries(
    node_id: UUID,
    period: TrafficPeriod = Query(TrafficPeriod.DAY),
    side: str = Query("auto", pattern="^(auto|entry|backend)$"),
    resolution_seconds: int | None = Query(None, ge=30, le=86400),
    service: NodeTrafficService = Depends(get_node_traffic_service),
) -> NodeTimeseriesOut:
    return await service.node_timeseries(
        node_id=node_id,
        period=period,
        side=side,
        resolution_seconds=resolution_seconds,
    )


@router.get(
    "/pairs",
    response_model=NodePairListOut,
    status_code=status.HTTP_200_OK,
    summary="Entry × backend traffic matrix",
)
async def node_pair_matrix(
    period: TrafficPeriod = Query(TrafficPeriod.DAY),
    service: NodeTrafficService = Depends(get_node_traffic_service),
) -> NodePairListOut:
    return await service.pair_matrix(period=period)
