from uuid import UUID

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from services.vpn.subscriptions.exceptions import SubscriptionNotFound
from services.vpn.subscriptions.model import Subscription
from shared.database.base_repository import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, session: AsyncSession):
        super().__init__(Subscription, session)

    async def get_by_token_hash(self, token_hash: str) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.token_hash == token_hash
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_any_token_hash(self, token_hash: str) -> Subscription | None:
        stmt = select(Subscription).where(
            or_(
                Subscription.token_hash == token_hash,
                Subscription.prev_token_hash == token_hash,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user_id(
            self,
            user_id: UUID,
            active_only: bool = False) -> list[Subscription]:
        stmt = select(Subscription).where(
            Subscription.user_id == user_id
        )
        if active_only:
            stmt = stmt.where(Subscription.is_active.is_(True))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate(self, subscription_id: UUID) -> None:
        sub = await self.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound
        sub.is_active = False
        await self.session.flush()