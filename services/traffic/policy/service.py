from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.traffic.policy.repository import TrafficPolicyRepository
from services.traffic.policy.schemas import TrafficPolicyOut, TrafficPolicyUpdateIn
from shared.database.session import AsyncDatabase


class TrafficPolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TrafficPolicyRepository(session)

    async def get(self) -> TrafficPolicyOut:
        rows = await self.repo.list(limit=1)
        return TrafficPolicyOut.model_validate(rows[0])

    async def update(self, data: TrafficPolicyUpdateIn) -> TrafficPolicyOut:
        rows = await self.repo.list(limit=1)
        policy = rows[0]
        payload = data.model_dump(exclude_unset=True, exclude_none=True)
        if payload:
            policy = await self.repo.update_by_id(policy.id, payload)
        return TrafficPolicyOut.model_validate(policy)


def get_traffic_policy_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> TrafficPolicyService:
    return TrafficPolicyService(session)
