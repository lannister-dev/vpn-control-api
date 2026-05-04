from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from services.admin_audit.service import AdminAuditService, get_admin_audit_service
from services.auth.dependencies import admin_auth, current_admin_actor
from services.routing.entry.schemas import (
    KeyRoutingOverrideIn,
    KeyRoutingOverrideOut,
    RoutingStateOut,
)
from services.routing.entry.service import EntryRoutingAdminService, get_entry_routing_admin_service

router = APIRouter(
    prefix="/admin/routing/entry",
    tags=["Admin Entry Routing"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "/state",
    response_model=RoutingStateOut,
    summary="List backends in entry-routing pool + active keys with current overrides",
)
async def get_state(
    service: EntryRoutingAdminService = Depends(get_entry_routing_admin_service),
) -> RoutingStateOut:
    return await service.get_state()


@router.patch(
    "/keys/{key_id}/override",
    response_model=KeyRoutingOverrideOut,
    summary="Force per-key sing-box outbound (admin override)",
)
async def set_key_override(
    key_id: UUID,
    data: KeyRoutingOverrideIn,
    actor: str = Depends(current_admin_actor),
    audit: AdminAuditService = Depends(get_admin_audit_service),
    service: EntryRoutingAdminService = Depends(get_entry_routing_admin_service),
) -> KeyRoutingOverrideOut:
    change = await service.set_key_override(key_id=key_id, backend_tag=data.backend_tag)
    if change is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found",
        )
    if change.changed:
        await audit.record(
            actor=actor,
            action="entry_routing_override_set" if change.current else "entry_routing_override_clear",
            target=str(key_id),
            summary=(
                f"forced outbound={change.current}" if change.current else "cleared outbound override"
            ),
            details={
                "key_id": str(key_id),
                "previous": change.previous,
                "current": change.current,
            },
        )
    return change.key
