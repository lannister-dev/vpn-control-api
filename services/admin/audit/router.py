from fastapi import APIRouter, Depends, Query, status

from services.admin.audit.schemas import AdminAuditListOut
from services.admin.audit.service import AdminAuditService, get_admin_audit_service
from services.auth.dependencies import admin_auth

router = APIRouter(
    prefix="/admin/audit",
    tags=["Admin Audit"],
    dependencies=[Depends(admin_auth)],
)


@router.get(
    "",
    response_model=AdminAuditListOut,
    status_code=status.HTTP_200_OK,
    summary="Recent admin actions audit log",
)
async def list_audit(
    action: str | None = Query(None, max_length=64),
    actor: str | None = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: AdminAuditService = Depends(get_admin_audit_service),
) -> AdminAuditListOut:
    return await service.list_recent(action=action, actor=actor, limit=limit, offset=offset)
