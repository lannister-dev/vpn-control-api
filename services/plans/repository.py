from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.plans.models import Plan
from shared.database.base_repository import BaseRepository


class PlanRepository(BaseRepository[Plan]):
    def __init__(self, session: AsyncSession):
        super().__init__(Plan, session)

    async def get_by_name(self, name: str) -> Plan | None:
        result = await self.session.execute(
            select(Plan).where(Plan.name == name)
        )
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = False) -> tuple[list[Plan], int]:
        stmt = select(Plan)
        count_stmt = select(func.count(Plan.id))

        if active_only:
            stmt = stmt.where(Plan.is_active)
            count_stmt = count_stmt.where(Plan.is_active)

        total = (await self.session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(Plan.sort_order.asc(), Plan.name.asc())
        rows = (await self.session.execute(stmt)).scalars().all()

        return list(rows), total
