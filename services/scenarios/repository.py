from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.plans.models import Plan
from services.scenarios.constants import ScenarioStatus
from services.scenarios.models import ScenarioCampaign, ScenarioState
from services.vpn.subscriptions.models import Subscription
from shared.database.base_repository import BaseRepository


class ScenarioRepository(BaseRepository[ScenarioState]):
    def __init__(self, session: AsyncSession):
        super().__init__(ScenarioState, session)

    async def active_campaigns_by_trigger(self, trigger_event: str) -> list[ScenarioCampaign]:
        stmt = (
            select(ScenarioCampaign)
            .where(
                ScenarioCampaign.is_active.is_(True),
                ScenarioCampaign.trigger_event == trigger_event,
            )
            .options(
                selectinload(ScenarioCampaign.nodes),
                selectinload(ScenarioCampaign.edges),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_state(self, user_id: UUID, campaign_id: UUID) -> ScenarioState | None:
        stmt = select(ScenarioState).where(
            ScenarioState.user_id == user_id,
            ScenarioState.campaign_id == campaign_id,
        )
        return await self.session.scalar(stmt)

    async def enroll(
        self,
        *,
        user_id: UUID,
        campaign_id: UUID,
        entered_at: datetime,
        next_send_at: datetime,
        current_node_key: str,
    ) -> bool:
        if await self.get_state(user_id, campaign_id) is not None:
            return False
        self.session.add(
            ScenarioState(
                user_id=user_id,
                campaign_id=campaign_id,
                current_node_key=current_node_key,
                status=ScenarioStatus.ACTIVE,
                entered_at=entered_at,
                next_send_at=next_send_at,
            )
        )
        await self.session.flush()
        return True

    async def list_due(self, *, now: datetime, limit: int) -> list[ScenarioState]:
        stmt = (
            select(ScenarioState)
            .where(
                ScenarioState.status == ScenarioStatus.ACTIVE,
                ScenarioState.next_send_at.isnot(None),
                ScenarioState.next_send_at <= now,
            )
            .order_by(ScenarioState.next_send_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_campaign_with_graph(self, campaign_id: UUID) -> ScenarioCampaign | None:
        stmt = (
            select(ScenarioCampaign)
            .where(ScenarioCampaign.id == campaign_id)
            .options(
                selectinload(ScenarioCampaign.nodes),
                selectinload(ScenarioCampaign.edges),
            )
        )
        return await self.session.scalar(stmt)

    async def list_campaigns(self) -> list[ScenarioCampaign]:
        stmt = (
            select(ScenarioCampaign)
            .options(
                selectinload(ScenarioCampaign.nodes),
                selectinload(ScenarioCampaign.edges),
            )
            .order_by(ScenarioCampaign.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def status_counts(self) -> list[tuple[UUID, str, int]]:
        stmt = select(
            ScenarioState.campaign_id,
            ScenarioState.status,
            func.count(),
        ).group_by(ScenarioState.campaign_id, ScenarioState.status)
        rows = await self.session.execute(stmt)
        return [(cid, status, int(n)) for cid, status, n in rows.all()]

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

    async def has_active_subscription(self, user_id: UUID, *, now: datetime) -> bool:
        stmt = (
            select(Subscription.id)
            .where(
                Subscription.user_id == user_id,
                Subscription.expires_at.is_not(None),
                Subscription.expires_at >= now,
            )
            .limit(1)
        )
        return await self.session.scalar(stmt) is not None
