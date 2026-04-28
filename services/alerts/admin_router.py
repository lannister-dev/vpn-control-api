from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.alerts.constants import LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT
from services.alerts.schemas import (
    AlertCountOut,
    AlertEventOut,
    AlertLevel,
    AlertListOut,
    AlertMarkAllReadOut,
)
from services.alerts.service import AlertService, get_alert_service
from services.auth.dependencies import admin_auth

router = APIRouter(
    prefix="/admin/alerts",
    tags=["Admin Alerts"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "",
    response_model=AlertListOut,
    status_code=status.HTTP_200_OK,
    summary="List recent system alerts",
)
async def list_alerts(
    unread_only: bool = Query(False),
    active_only: bool = Query(True),
    level: AlertLevel | None = Query(None),
    source: str | None = Query(None, max_length=64),
    limit: int = Query(LIST_DEFAULT_LIMIT, ge=1, le=LIST_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    service: AlertService = Depends(get_alert_service),
) -> AlertListOut:
    return await service.list_for_admin(
        unread_only=unread_only,
        active_only=active_only,
        level=level,
        source=source,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/unread-count",
    response_model=AlertCountOut,
    status_code=status.HTTP_200_OK,
    summary="Unread alerts counter for the bell badge",
)
async def unread_count(
    service: AlertService = Depends(get_alert_service),
) -> AlertCountOut:
    return AlertCountOut(unread=await service.count_unread())


@router.post(
    "/{alert_id}/read",
    response_model=AlertEventOut,
    status_code=status.HTTP_200_OK,
    summary="Mark a single alert as read",
)
async def mark_read(
    alert_id: UUID,
    service: AlertService = Depends(get_alert_service),
) -> AlertEventOut:
    row = await service.mark_read(alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return row


@router.post(
    "/mark-all-read",
    response_model=AlertMarkAllReadOut,
    status_code=status.HTTP_200_OK,
    summary="Mark all unread alerts as read",
)
async def mark_all_read(
    service: AlertService = Depends(get_alert_service),
) -> AlertMarkAllReadOut:
    return await service.mark_all_read()


@router.post(
    "/{alert_id}/dismiss",
    response_model=AlertEventOut,
    status_code=status.HTTP_200_OK,
    summary="Dismiss an alert (hide from active feed)",
)
async def dismiss(
    alert_id: UUID,
    service: AlertService = Depends(get_alert_service),
) -> AlertEventOut:
    row = await service.dismiss(alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return row
