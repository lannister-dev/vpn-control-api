from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from services.auth.dependencies import admin_auth
from services.traffic.nodes.schemas import FleetTimeseriesOut, TrafficPeriod
from services.traffic.nodes.service import NodeTrafficService, get_node_traffic_service
from services.traffic.users.schemas import (
    TrafficHistoryListOut,
    TrafficKeySummaryListOut,
    UserTrafficSummaryListOut,
)
from services.traffic.users.service import TrafficAdminService, get_traffic_admin_service

router = APIRouter(
    prefix="/admin/traffic",
    tags=["Admin Traffic"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "/timeseries",
    response_model=FleetTimeseriesOut,
    status_code=status.HTTP_200_OK,
    summary="Fleet-wide traffic timeseries bucketed by region",
    description=(
        "Returns bucketed timeseries of fleet traffic for the selected period, "
        "with per-region breakdown. Used by the Traffic dashboard stacked area chart."
    ),
)
async def fleet_timeseries(
    period: TrafficPeriod = Query(TrafficPeriod.DAY),
    node_service: NodeTrafficService = Depends(get_node_traffic_service),
) -> FleetTimeseriesOut:
    return await node_service.fleet_timeseries(period=period)


@router.get(
    "/users",
    response_model=UserTrafficSummaryListOut,
    status_code=status.HTTP_200_OK,
    summary="Top users by traffic for the selected period",
    description=(
        "Aggregates per-user traffic (sum of delta_bytes across all their VPN keys) "
        "for the selected period and returns top-N talkers."
    ),
)
async def top_users_by_traffic(
    period: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    limit: int = Query(10, ge=1, le=100),
    service: TrafficAdminService = Depends(get_traffic_admin_service),
) -> UserTrafficSummaryListOut:
    return await service.top_users_by_traffic(period=period, limit=limit)


@router.get(
    "/keys",
    response_model=TrafficKeySummaryListOut,
    status_code=status.HTTP_200_OK,
    summary="List VPN keys with traffic consumption summary",
    description=(
        "Returns a paginated list of VPN keys with their current traffic counters, "
        "limits, revocation status, and validity period. "
        "Supports filtering by user, revocation state, and free-text search "
        "across key id, client_id, and user_id."
    ),
)
async def list_traffic_keys(
    user_id: UUID | None = Query(
        None, description="Filter by user UUID",
    ),
    is_revoked: bool | None = Query(
        None, description="Filter by revocation status (true/false)",
    ),
    search: str | None = Query(
        None, max_length=128, description="Search by key id, client_id, or user_id",
    ),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of records to return",
    ),
    offset: int = Query(
        0, ge=0, description="Number of records to skip",
    ),
    service: TrafficAdminService = Depends(get_traffic_admin_service),
) -> TrafficKeySummaryListOut:
    return await service.list_keys_with_traffic(
        user_id=user_id,
        is_revoked=is_revoked,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/keys/{key_id}/history",
    response_model=TrafficHistoryListOut,
    status_code=status.HTTP_200_OK,
    summary="Get traffic usage history for a VPN key",
    description=(
        "Returns a paginated, reverse-chronological list of traffic delta records "
        "for the specified VPN key. Each record contains the delta bytes consumed "
        "and the total reported by the Xray node at that point. "
        "Supports date range filtering via date_from / date_to query parameters."
    ),
)
async def get_key_traffic_history(
    key_id: UUID,
    date_from: datetime | None = Query(
        None, description="Include records created at or after this timestamp (ISO 8601)",
    ),
    date_to: datetime | None = Query(
        None, description="Include records created at or before this timestamp (ISO 8601)",
    ),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of records to return",
    ),
    offset: int = Query(
        0, ge=0, description="Number of records to skip",
    ),
    service: TrafficAdminService = Depends(get_traffic_admin_service),
) -> TrafficHistoryListOut:
    return await service.get_key_traffic_history(
        key_id=key_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
