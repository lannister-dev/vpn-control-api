from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from services.traffic.model import TrafficUsage
from services.traffic.schemas import TrafficUsageCreate
from shared.database.base_repository import BaseRepository


class TrafficUsageRepository(BaseRepository[TrafficUsage]):
    def __init__(self, session: AsyncSession):
        super().__init__(TrafficUsage, session)

    async def bulk_create(self, rows: list[TrafficUsageCreate]) -> int:
        if not rows:
            return 0
        objects = [self.model(**row.model_dump()) for row in rows]
        self.session.add_all(objects)
        await self.session.flush()
        return len(objects)

    async def delete_older_than(self, *, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(self.model).where(self.model.created_at < cutoff)
        )
        rowcount = result.rowcount
        if callable(rowcount):
            rowcount = rowcount()
        if rowcount is None or rowcount < 0:
            return 0
        return int(rowcount)
