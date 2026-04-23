from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_transport.policy.model import TransportPolicy


class TransportPolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_current(self) -> TransportPolicy:
        result = await self.session.execute(select(TransportPolicy).limit(1))
        policy = result.scalar_one_or_none()
        if policy is None:
            policy = TransportPolicy()
            self.session.add(policy)
            await self.session.flush()
        return policy

    async def update(self, *, data: dict) -> TransportPolicy:
        policy = await self.get_current()
        for key, value in data.items():
            if value is not None:
                setattr(policy, key, value)
        await self.session.flush()
        return policy
