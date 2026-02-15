from uuid import UUID

from sqlalchemy import select, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.vpn.subscriptions.exceptions import SubscriptionNotFound
from services.vpn.subscriptions.model import Subscription, SubscriptionDevice
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


class SubscriptionDeviceRepository(BaseRepository[SubscriptionDevice]):
    def __init__(self, session: AsyncSession):
        super().__init__(SubscriptionDevice, session)

    async def get_active_by_sub_and_hwid_hash(
            self,
            *,
            subscription_id: UUID,
            hwid_hash: str,
    ) -> SubscriptionDevice | None:
        res = await self.session.execute(
            select(SubscriptionDevice).where(
                SubscriptionDevice.subscription_id == subscription_id,
                SubscriptionDevice.hwid_hash == hwid_hash,
                SubscriptionDevice.is_active.is_(True),
            )
        )
        return res.scalar_one_or_none()

    async def count_active_for_subscription(self, subscription_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count())
            .select_from(SubscriptionDevice)
            .where(
                SubscriptionDevice.subscription_id == subscription_id,
                SubscriptionDevice.is_active.is_(True),
            )
        )
        return int(res.scalar_one())

    async def touch(
            self,
            *,
            device_id: UUID,
            last_seen_at,
            user_agent: str | None,
    ) -> None:
        await self.session.execute(
            update(SubscriptionDevice)
            .where(SubscriptionDevice.id == device_id)
            .values(last_seen_at=last_seen_at, user_agent=user_agent)
        )
