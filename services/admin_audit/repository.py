from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_audit.model import AdminAuditRecord


class AdminAuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        actor: str,
        action: str,
        target: str | None = None,
        summary: str | None = None,
        details: dict | None = None,
    ) -> AdminAuditRecord:
        row = AdminAuditRecord(
            actor=actor,
            action=action,
            target=target,
            summary=summary,
            details=details or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_paginated(
        self,
        *,
        action: str | None = None,
        actor: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AdminAuditRecord], int]:
        base = select(AdminAuditRecord)
        if action:
            base = base.where(AdminAuditRecord.action == action)
        if actor:
            base = base.where(AdminAuditRecord.actor == actor)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = base.order_by(AdminAuditRecord.created_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        return rows, total
