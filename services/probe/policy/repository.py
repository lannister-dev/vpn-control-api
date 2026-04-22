from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.probe.policy.model import ProbePolicy


class ProbePolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_current(self) -> ProbePolicy:
        result = await self.session.execute(select(ProbePolicy).limit(1))
        policy = result.scalar_one_or_none()
        if policy is None:
            policy = ProbePolicy()
            self.session.add(policy)
            await self.session.flush()
        return policy

    async def update(self, *, data: dict) -> ProbePolicy:
        policy = await self.get_current()
        for key, value in data.items():
            if value is not None:
                setattr(policy, key, value)
        await self.session.flush()
        return policy
