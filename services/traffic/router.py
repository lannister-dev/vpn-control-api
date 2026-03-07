from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from services.auth.dependencies import admin_auth
from services.traffic.schemas import TrafficHistoryListOut, TrafficKeySummaryListOut
from services.traffic.service import TrafficAdminService, get_traffic_admin_service

router = APIRouter(
    prefix="/admin/traffic",
    tags=["Admin Traffic"],
    dependencies=[Depends(admin_auth)],
)


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
