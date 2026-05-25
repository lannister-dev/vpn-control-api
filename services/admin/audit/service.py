from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin.audit.repository import AdminAuditRepository
from services.admin.audit.schemas import (
    AdminAuditListOut,
    AdminAuditRecordCreate,
    AdminAuditRecordOut,
)
from shared.database.session import AsyncDatabase


class AdminAuditService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AdminAuditRepository(session)

    async def record(
        self,
        *,
        actor: str,
        action: str,
        target: str | None = None,
        summary: str | None = None,
        details: dict | None = None,
    ) -> None:
        record = AdminAuditRecordCreate(
            actor=actor,
            action=action,
            target=target,
            summary=summary,
            details=details or {},
        )
        await self.repo.create(record.model_dump())

    async def list_recent(
        self,
        *,
        action: str | None = None,
        actor: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminAuditListOut:
        rows, total = await self.repo.list_paginated(
            action=action, actor=actor, limit=limit, offset=offset,
        )
        return AdminAuditListOut(
            items=[AdminAuditRecordOut.model_validate(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


def get_admin_audit_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> AdminAuditService:
    return AdminAuditService(session)
