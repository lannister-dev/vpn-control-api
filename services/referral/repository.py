from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.referral.models import Referral
from shared.database.base_repository import BaseRepository


class ReferralRepository(BaseRepository[Referral]):
    def __init__(self, session: AsyncSession):
        super().__init__(Referral, session)

    async def get_by_referred_user(self, referred_user_id: UUID) -> Referral | None:
        result = await self.session.execute(
            select(Referral).where(Referral.referred_user_id == referred_user_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_referred_user(self, referred_user_id: UUID) -> Referral | None:
        result = await self.session.execute(
            select(Referral).where(
                Referral.referred_user_id == referred_user_id,
                Referral.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def count_by_referrer(self, referrer_user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_user_id == referrer_user_id,
            )
        )
        return result.scalar_one()

    async def count_rewarded_by_referrer(self, referrer_user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_user_id == referrer_user_id,
                Referral.status == "rewarded",
            )
        )
        return result.scalar_one()

    async def sum_rewards_by_referrer(self, referrer_user_id: UUID) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Referral.reward_amount), 0)).where(
                Referral.referrer_user_id == referrer_user_id,
                Referral.status == "rewarded",
            )
        )
        return float(result.scalar_one())
