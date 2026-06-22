from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.drip.constants import DripStatus
from services.drip.models import DripCampaign, UserCampaignState
from services.plans.models import Plan
from services.vpn.subscriptions.models import Subscription
from shared.database.base_repository import BaseRepository


class DripRepository(BaseRepository[UserCampaignState]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserCampaignState, session)

    async def active_campaigns_by_trigger(self, trigger_event: str) -> list[DripCampaign]:
        stmt = (
            select(DripCampaign)
            .where(
                DripCampaign.is_active.is_(True),
                DripCampaign.trigger_event == trigger_event,
            )
            .options(selectinload(DripCampaign.steps))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_state(self, user_id: UUID, campaign_id: UUID) -> UserCampaignState | None:
        stmt = select(UserCampaignState).where(
            UserCampaignState.user_id == user_id,
            UserCampaignState.campaign_id == campaign_id,
        )
        return await self.session.scalar(stmt)

    async def enroll(
        self, *, user_id: UUID, campaign_id: UUID, entered_at: datetime, next_send_at: datetime
    ) -> bool:
        if await self.get_state(user_id, campaign_id) is not None:
            return False
        self.session.add(
            UserCampaignState(
                user_id=user_id,
                campaign_id=campaign_id,
                current_step=0,
                status=DripStatus.ACTIVE,
                entered_at=entered_at,
                next_send_at=next_send_at,
            )
        )
        await self.session.flush()
        return True

    async def list_due(self, *, now: datetime, limit: int) -> list[UserCampaignState]:
        stmt = (
            select(UserCampaignState)
            .where(
                UserCampaignState.status == DripStatus.ACTIVE,
                UserCampaignState.next_send_at.isnot(None),
                UserCampaignState.next_send_at <= now,
            )
            .order_by(UserCampaignState.next_send_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_campaign_with_steps(self, campaign_id: UUID) -> DripCampaign | None:
        stmt = (
            select(DripCampaign)
            .where(DripCampaign.id == campaign_id)
            .options(selectinload(DripCampaign.steps))
        )
        return await self.session.scalar(stmt)

    async def has_connected(self, user_id: UUID) -> bool:
        stmt = (
            select(Subscription.id)
            .where(
                Subscription.user_id == user_id,
                Subscription.first_connected_at.isnot(None),
            )
            .limit(1)
        )
        return await self.session.scalar(stmt) is not None

    async def has_paid(self, user_id: UUID) -> bool:
        stmt = (
            select(Subscription.id)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.user_id == user_id, Plan.price_rub > 0)
            .limit(1)
        )
        return await self.session.scalar(stmt) is not None
