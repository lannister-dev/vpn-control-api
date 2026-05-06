from datetime import datetime, timedelta, timezone

from sqlalchemy import String, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.users.models import User
from shared.database.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        tag: str | None = None,
        has_debt: bool | None = None,
        has_subscription: bool | None = None,
        expiring_within_days: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        from services.vpn.subscriptions.model import Subscription

        stmt = select(User)
        count_stmt = select(func.count(User.id))

        def add(clause):
            nonlocal stmt, count_stmt
            stmt = stmt.where(clause)
            count_stmt = count_stmt.where(clause)

        if search:
            pattern = f"%{search}%"
            add(or_(
                User.username.ilike(pattern),
                User.telegram_id.cast(String).ilike(pattern),
                User.id.cast(String).ilike(pattern),
                User.tag.ilike(pattern),
            ))

        if is_active is not None:
            add(User.is_active == is_active)

        if tag:
            add(User.tag == tag)

        if has_debt is True:
            add(User.balance < 0)
        elif has_debt is False:
            add(User.balance >= 0)

        if has_subscription is not None:
            sub_exists = exists().where(Subscription.user_id == User.id)
            add(sub_exists if has_subscription else ~sub_exists)

        if expiring_within_days is not None:
            now = datetime.now(timezone.utc)
            horizon = now + timedelta(days=int(expiring_within_days))
            expiring_exists = exists().where(
                (Subscription.user_id == User.id)
                & (Subscription.is_active.is_(True))
                & (Subscription.expires_at.isnot(None))
                & (Subscription.expires_at >= now)
                & (Subscription.expires_at <= horizon)
            )
            add(expiring_exists)

        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().all()

        return list(rows), total

    async def count_subscriptions(self, user_id) -> int:
        from services.vpn.subscriptions.model import Subscription

        result = await self.session.execute(
            select(func.count(Subscription.id)).where(Subscription.user_id == user_id)
        )
        return result.scalar() or 0

    async def count_keys(self, user_id) -> int:
        from services.vpn.keys.models import VpnKey

        result = await self.session.execute(
            select(func.count(VpnKey.id)).where(VpnKey.user_id == user_id)
        )
        return result.scalar() or 0
