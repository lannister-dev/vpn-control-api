from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from services.vpn.subscriptions.exceptions import SubscriptionNotFound
from services.vpn.subscriptions.model import (
    Subscription,
    SubscriptionDevice,
    SubscriptionDeviceKey,
)
from shared.database.base_repository import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, session: AsyncSession):
        super().__init__(Subscription, session)

    async def list_by_ids_with_plan(self, ids: list[UUID]) -> list[Subscription]:
        if not ids:
            return []
        stmt = (
            select(self.model)
            .options(joinedload(self.model.plan))
            .where(self.model.id.in_(ids))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def list_needing_traffic_reset(self, *, strategy: str, reset_before) -> list[Subscription]:
        """Find active subscriptions with given reset strategy whose last reset is before cutoff."""
        from services.plans.models import Plan
        stmt = (
            select(self.model)
            .join(Plan, self.model.plan_id == Plan.id)
            .options(joinedload(self.model.plan))
            .where(
                self.model.is_active.is_(True),
                Plan.is_active.is_(True),
                Plan.reset_strategy == strategy,
                Plan.traffic_limit_bytes > 0,
                or_(
                    self.model.last_traffic_reset_at.is_(None),
                    self.model.last_traffic_reset_at < reset_before,
                ),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_by_token_hash(self, token_hash: str) -> Subscription | None:
        stmt = select(self.model).where(self.model.token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_any_token_hash(self, token_hash: str) -> Subscription | None:
        stmt = select(self.model).where(
            or_(
                self.model.token_hash == token_hash,
                self.model.prev_token_hash == token_hash,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user_id(
            self,
            user_id: UUID,
            active_only: bool = False,
    ) -> list[Subscription]:
        stmt = select(self.model).where(self.model.user_id == user_id)
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate(self, subscription_id: UUID) -> None:
        sub = await self.get_by_id(subscription_id)
        if not sub:
            raise SubscriptionNotFound
        sub.is_active = False
        await self.session.flush()

    async def find_active_subscription(self, user_id: UUID, plan_id: UUID):
        result = await self.session.execute(
            select(self.model).where(
                self.model.user_id == user_id,
                self.model.plan_id == plan_id,
                self.model.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()


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
            select(self.model).where(
                self.model.subscription_id == subscription_id,
                self.model.hwid_hash == hwid_hash,
                self.model.is_active.is_(True),
            )
        )
        return res.scalar_one_or_none()

    async def count_active_for_subscription(self, subscription_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.subscription_id == subscription_id,
                self.model.is_active.is_(True),
            )
        )
        return int(res.scalar_one())

    async def list_by_subscription(
            self,
            subscription_id: UUID,
            *,
            active_only: bool = False,
    ) -> list[SubscriptionDevice]:
        stmt = select(self.model).where(
            self.model.subscription_id == subscription_id,
        )
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        stmt = stmt.order_by(self.model.created_at.desc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_by_id_for_subscription(
            self,
            *,
            subscription_id: UUID,
            device_id: UUID,
    ) -> SubscriptionDevice | None:
        res = await self.session.execute(
            select(self.model).where(
                self.model.id == device_id,
                self.model.subscription_id == subscription_id,
            )
        )
        return res.scalar_one_or_none()

    async def list_key_ids_for_subscription(
            self,
            subscription_id: UUID,
            *,
            active_only: bool = False,
    ) -> list[UUID]:
        bundle_stmt = (
            select(SubscriptionDeviceKey.vpn_key_id)
            .join(
                self.model,
                SubscriptionDeviceKey.subscription_device_id == self.model.id,
            )
            .where(self.model.subscription_id == subscription_id)
        )
        if active_only:
            bundle_stmt = bundle_stmt.where(
                self.model.is_active.is_(True),
                SubscriptionDeviceKey.is_active.is_(True),
            )
        bundle_res = await self.session.execute(bundle_stmt)
        key_ids = [row[0] for row in bundle_res.all() if row[0] is not None]
        return list(dict.fromkeys(key_ids))

    async def touch(
            self,
            *,
            device_id: UUID,
            last_seen_at,
            user_agent: str | None,
    ) -> None:
        await self.session.execute(
            update(self.model)
            .where(self.model.id == device_id)
            .values(last_seen_at=last_seen_at, user_agent=user_agent)
        )


class SubscriptionDeviceKeyRepository(BaseRepository[SubscriptionDeviceKey]):
    def __init__(self, session: AsyncSession):
        super().__init__(SubscriptionDeviceKey, session)

    async def list_by_device(
            self,
            subscription_device_id: UUID,
            *,
            active_only: bool = False,
    ) -> list[SubscriptionDeviceKey]:
        stmt = select(self.model).where(
            self.model.subscription_device_id == subscription_device_id,
        )
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        stmt = stmt.order_by(self.model.is_primary.desc(), self.model.created_at.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_by_device_ids(
            self,
            subscription_device_ids: list[UUID],
            *,
            active_only: bool = False,
    ) -> list[SubscriptionDeviceKey]:
        normalized = list(dict.fromkeys(subscription_device_ids))
        if not normalized:
            return []

        stmt = select(self.model).where(
            self.model.subscription_device_id.in_(normalized),
        )
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        stmt = stmt.order_by(
            self.model.subscription_device_id.asc(),
            self.model.is_primary.desc(),
            self.model.created_at.asc(),
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

