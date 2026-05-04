from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_audit.service import AdminAuditService, get_admin_audit_service
from services.auth.dependencies import admin_auth, current_admin_actor
from services.vpn.keys.repository import VpnKeyRepository
from shared.database.session import AsyncDatabase

router = APIRouter(
    prefix="/admin/routing/entry",
    tags=["Admin Entry Routing"],
    dependencies=[Depends(admin_auth)],
)


class KeyRoutingOverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend_tag: str | None = Field(default=None, max_length=128)


class KeyRoutingOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key_id: UUID
    client_id: str
    entry_routing_override_backend_tag: str | None


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
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> KeyRoutingOverrideOut:
    repo = VpnKeyRepository(session)
    key = await repo.get_by_id(key_id)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found",
        )
    new_tag = (data.backend_tag or "").strip() or None
    if new_tag != key.entry_routing_override_backend_tag:
        await repo.update_by_id(
            key_id,
            {"entry_routing_override_backend_tag": new_tag},
        )
        key.entry_routing_override_backend_tag = new_tag
        await audit.record(
            actor=actor,
            action="entry_routing_override_set" if new_tag else "entry_routing_override_clear",
            target=str(key_id),
            summary=(
                f"forced outbound={new_tag}" if new_tag else "cleared outbound override"
            ),
            details={"key_id": str(key_id), "backend_tag": new_tag},
        )
    return KeyRoutingOverrideOut(
        key_id=key.id,
        client_id=key.client_id,
        entry_routing_override_backend_tag=key.entry_routing_override_backend_tag,
    )
