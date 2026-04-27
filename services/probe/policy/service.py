from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.probe.policy.repository import ProbePolicyRepository
from services.probe.policy.schemas import ProbePolicyOut, ProbePolicyUpdateIn
from shared.database.session import AsyncDatabase


class ProbePolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProbePolicyRepository(session)

    async def get(self) -> ProbePolicyOut:
        rows = await self.repo.list(limit=1)
        return ProbePolicyOut.model_validate(rows[0])

    async def update(self, data: ProbePolicyUpdateIn) -> ProbePolicyOut:
        rows = await self.repo.list(limit=1)
        policy = rows[0]
        payload = data.model_dump(exclude_unset=True, exclude_none=True)
        if payload:
            policy = await self.repo.update_by_id(policy.id, payload)
        return ProbePolicyOut.model_validate(policy)


def get_probe_policy_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> ProbePolicyService:
    return ProbePolicyService(session)
