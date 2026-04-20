from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.zones.models import Zone
from shared.database.base_repository import BaseRepository


class ZoneRepository(BaseRepository[Zone]):
    def __init__(self, session: AsyncSession):
        super().__init__(Zone, session)

    async def get_by_code(self, code: str) -> Zone | None:
        result = await self.session.execute(select(Zone).where(Zone.code == code))
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = False) -> tuple[list[Zone], int]:
        stmt = select(Zone)
        count_stmt = select(func.count(Zone.id))

        if active_only:
            stmt = stmt.where(Zone.is_active.is_(True))
            count_stmt = count_stmt.where(Zone.is_active.is_(True))

        total = (await self.session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(Zone.sort_order.asc(), Zone.code.asc())
        rows = (await self.session.execute(stmt)).scalars().all()

        return list(rows), total
