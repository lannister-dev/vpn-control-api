from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.plans.models import Plan
from services.traffic.users.models import TrafficUsage
from services.traffic.users.schemas import TrafficUsageCreate
from services.users.models import User
from services.vpn.keys.models import VpnKey
from services.vpn.subscriptions.models import Subscription
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

    async def top_users_by_bytes(
        self,
        *,
        from_ts: datetime,
        to_ts: datetime,
        limit: int,
    ) -> list[tuple[UUID, int | None, str | None, str | None, int, int]]:
        total_bytes = func.coalesce(func.sum(self.model.delta_bytes), 0).label("total_bytes")
        key_count = func.count(func.distinct(VpnKey.id)).label("keys")
        plan_name = func.max(Plan.name).label("plan_name")

        stmt = (
            select(
                User.id,
                User.telegram_id,
                User.username,
                plan_name,
                total_bytes,
                key_count,
            )
            .join(VpnKey, VpnKey.id == self.model.key_id)
            .join(User, User.id == VpnKey.user_id)
            .outerjoin(Subscription, Subscription.id == VpnKey.subscription_id)
            .outerjoin(Plan, Plan.id == Subscription.plan_id)
            .where(self.model.created_at >= from_ts)
            .where(self.model.created_at < to_ts)
            .group_by(User.id, User.telegram_id, User.username)
            .order_by(total_bytes.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            (row[0], row[1], row[2], row[3], int(row[4]), int(row[5]))
            for row in result.all()
        ]

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
