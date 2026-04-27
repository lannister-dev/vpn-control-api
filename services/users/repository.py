from sqlalchemy import String, func, or_, select
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
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        stmt = select(User)
        count_stmt = select(func.count(User.id))

        if search:
            pattern = f"%{search}%"
            search_filter = or_(
                User.username.ilike(pattern),
                User.telegram_id.cast(String).ilike(pattern),
                User.id.cast(String).ilike(pattern),
                User.tag.ilike(pattern),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)

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
