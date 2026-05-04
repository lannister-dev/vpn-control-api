from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from services.admin_audit.service import AdminAuditService, get_admin_audit_service
from services.auth.dependencies import admin_auth, current_admin_actor
from services.config import get_settings
from services.routing.entry.service import EntryRoutingService
from services.users.models import User
from services.vpn.keys.models import VpnKey
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


class RoutingBackendOut(BaseModel):
    tag: str
    server: str
    server_port: int


class RoutingKeyRowOut(BaseModel):
    key_id: UUID
    client_id: str
    user_id: UUID
    user_username: str | None = None
    user_telegram_id: int | None = None
    subscription_id: UUID | None = None
    transport: str
    is_revoked: bool
    override: str | None = None


class RoutingStateOut(BaseModel):
    backends: list[RoutingBackendOut]
    keys: list[RoutingKeyRowOut]


@router.get(
    "/state",
    response_model=RoutingStateOut,
    summary="List backends in entry-routing pool + active keys with current overrides",
)
async def get_state(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> RoutingStateOut:
    settings = get_settings()
    service = EntryRoutingService(session, config=settings.entry_routing)
    entries = await service.list_target_nodes()
    backends_by_tag: dict[str, RoutingBackendOut] = {}
    for entry in entries:
        for b in await service._build_backends_for_zone(entry):
            if b.tag not in backends_by_tag:
                backends_by_tag[b.tag] = RoutingBackendOut(
                    tag=b.tag, server=b.server, server_port=b.server_port,
                )

    stmt = (
        select(VpnKey)
        .options(joinedload(VpnKey.user))
        .where(VpnKey.is_revoked.is_(False))
        .order_by(VpnKey.created_at.desc())
        .limit(500)
    )
    rows = (await session.execute(stmt)).scalars().all()

    user_rows: dict[UUID, User] = {k.user_id: k.user for k in rows if k.user is not None}

    keys: list[RoutingKeyRowOut] = []
    for k in rows:
        u = user_rows.get(k.user_id)
        keys.append(
            RoutingKeyRowOut(
                key_id=k.id,
                client_id=k.client_id,
                user_id=k.user_id,
                user_username=getattr(u, "username", None) if u is not None else None,
                user_telegram_id=getattr(u, "telegram_id", None) if u is not None else None,
                subscription_id=k.subscription_id,
                transport=k.transport,
                is_revoked=k.is_revoked,
                override=k.entry_routing_override_backend_tag,
            )
        )

    return RoutingStateOut(
        backends=sorted(backends_by_tag.values(), key=lambda x: x.tag),
        keys=keys,
    )


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
