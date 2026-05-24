from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_audit.models import AdminAuditRecord
from shared.database.base_repository import BaseRepository


class AdminAuditRepository(BaseRepository[AdminAuditRecord]):
    def __init__(self, session: AsyncSession):
        super().__init__(AdminAuditRecord, session)

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
