from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from services.admin_transport.schemas import (
    EventLogListOut,
    ForceSnapshotOut,
    OutboxBreakdownOut,
    OutboxListOut,
    OutboxRetryAllOut,
    OutboxRetryOut,
    TransportCleanupOut,
    TransportNodeDetailOut,
    TransportNodeListOut,
    TransportOverviewOut,
)
from services.admin_transport.service import (
    AdminTransportService,
    get_admin_transport_service,
)
from services.auth.dependencies import admin_auth

router = APIRouter(
    prefix="/admin/transport",
    tags=["Admin Transport"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "/overview",
    response_model=TransportOverviewOut,
    status_code=status.HTTP_200_OK,
    summary="NATS transport overview with KPIs",
)
async def transport_overview(
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> TransportOverviewOut:
    return await service.get_overview()


@router.get(
    "/nodes",
    response_model=TransportNodeListOut,
    status_code=status.HTTP_200_OK,
    summary="List nodes with transport state",
)
async def transport_nodes(
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> TransportNodeListOut:
    return await service.list_transport_nodes()


@router.get(
    "/nodes/{node_id}",
    response_model=TransportNodeDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Node transport detail with events and outbox",
)
async def transport_node_detail(
    node_id: UUID,
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> TransportNodeDetailOut:
    return await service.get_transport_node_detail(node_id)


@router.get(
    "/outbox",
    response_model=OutboxListOut,
    status_code=status.HTTP_200_OK,
    summary="Browse outbox queue",
)
async def transport_outbox(
    node_id: UUID | None = Query(None, description="Filter by node"),
    status_filter: str | None = Query(None, alias="status", description="pending|failed|publishing|published"),
    event_type: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> OutboxListOut:
    return await service.list_outbox(
        node_id=node_id,
        status_filter=status_filter,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/outbox/{outbox_id}/retry",
    response_model=OutboxRetryOut,
    status_code=status.HTTP_200_OK,
    summary="Retry a failed outbox item",
)
async def transport_outbox_retry(
    outbox_id: UUID,
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> OutboxRetryOut:
    return await service.retry_outbox_item(outbox_id)


@router.get(
    "/outbox/breakdown",
    response_model=OutboxBreakdownOut,
    status_code=status.HTTP_200_OK,
    summary="Outbox counts grouped by event_type and status",
)
async def transport_outbox_breakdown(
    node_id: UUID | None = Query(None, description="Filter by node"),
    status_filter: str | None = Query(None, alias="status", description="Filter: pending/failed/publishing/published"),
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> OutboxBreakdownOut:
    items = await service.outbox_breakdown_by_type(node_id=node_id, status_filter=status_filter)
    return OutboxBreakdownOut(items=items)


@router.post(
    "/outbox/{outbox_id}/cancel",
    response_model=OutboxRetryOut,
    status_code=status.HTTP_200_OK,
    summary="Cancel a pending/failed outbox item (removes it from queue)",
)
async def transport_outbox_cancel(
    outbox_id: UUID,
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> OutboxRetryOut:
    return await service.cancel_outbox_item(outbox_id)


@router.post(
    "/outbox/retry-all-failed",
    response_model=OutboxRetryAllOut,
    status_code=status.HTTP_200_OK,
    summary="Retry all failed outbox items",
)
async def transport_outbox_retry_all(
    node_id: UUID | None = Query(None, description="Scope to specific node"),
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> OutboxRetryAllOut:
    return await service.retry_all_failed(node_id)


@router.get(
    "/events",
    response_model=EventLogListOut,
    status_code=status.HTTP_200_OK,
    summary="Browse event log",
)
async def transport_events(
    node_id: UUID | None = Query(None, description="Filter by node"),
    event_type: str | None = Query(None, description="Filter by event type"),
    date_from: datetime | None = Query(None, description="From date (UTC)"),
    date_to: datetime | None = Query(None, description="To date (UTC)"),
    search: str | None = Query(None, max_length=255, description="Search event_id"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> EventLogListOut:
    return await service.list_events(
        node_id=node_id,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/cleanup",
    response_model=TransportCleanupOut,
    status_code=status.HTTP_200_OK,
    summary="Delete old transport event log and published outbox rows",
)
async def transport_cleanup(
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> TransportCleanupOut:
    return await service.cleanup_old_data()


@router.post(
    "/nodes/{node_id}/request-snapshot",
    response_model=ForceSnapshotOut,
    status_code=status.HTTP_200_OK,
    summary="Force snapshot generation for a node",
)
async def transport_force_snapshot(
    node_id: UUID,
    service: AdminTransportService = Depends(get_admin_transport_service),
) -> ForceSnapshotOut:
    return await service.force_snapshot(node_id)
