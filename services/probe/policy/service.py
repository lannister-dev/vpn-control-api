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
        policy = await self.repo.get_current()
        await self.session.commit()
        return ProbePolicyOut.model_validate(policy)

    async def update(self, data: ProbePolicyUpdateIn) -> ProbePolicyOut:
        payload = data.model_dump(exclude_unset=True)
        policy = await self.repo.update(data=payload)
        await self.session.commit()
        return ProbePolicyOut.model_validate(policy)


def get_probe_policy_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> ProbePolicyService:
    return ProbePolicyService(session)
