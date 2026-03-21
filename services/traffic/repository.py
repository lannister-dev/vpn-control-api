from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.traffic.model import KeyNodeTrafficCounter, TrafficUsage
from services.traffic.schemas import TrafficUsageCreate
from shared.database.base_repository import BaseRepository


class KeyNodeTrafficCounterRepository(BaseRepository[KeyNodeTrafficCounter]):
    def __init__(self, session: AsyncSession):
        super().__init__(KeyNodeTrafficCounter, session)

    async def get_counters_for_keys(
        self, key_ids: list[UUID],
    ) -> dict[tuple[UUID, str], KeyNodeTrafficCounter]:
        if not key_ids:
            return {}
        stmt = select(KeyNodeTrafficCounter).where(
            KeyNodeTrafficCounter.key_id.in_(key_ids),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return {(r.key_id, r.node_id): r for r in rows}

    async def delete_by_key_ids(self, key_ids: list[UUID]) -> int:
        if not key_ids:
            return 0
        result = await self.session.execute(
            delete(KeyNodeTrafficCounter).where(
                KeyNodeTrafficCounter.key_id.in_(key_ids),
            )
        )
        return result.rowcount or 0


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

    async def list_by_key_id(
        self,
        *,
        key_id: UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TrafficUsage], int]:
        conditions = [self.model.key_id == key_id]
        if date_from is not None:
            conditions.append(self.model.created_at >= date_from)
        if date_to is not None:
            conditions.append(self.model.created_at <= date_to)

        count_stmt = select(func.count(self.model.id))
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = select(self.model)
        for cond in conditions:
            stmt = stmt.where(cond)
        stmt = stmt.order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        return rows, total

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
