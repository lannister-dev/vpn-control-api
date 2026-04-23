from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.policy.model import NodePolicy


class NodePolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_current(self) -> NodePolicy:
        result = await self.session.execute(select(NodePolicy).limit(1))
        policy = result.scalar_one_or_none()
        if policy is None:
            policy = NodePolicy()
            self.session.add(policy)
            await self.session.flush()
        return policy

    async def update(self, *, data: dict) -> NodePolicy:
        policy = await self.get_current()
        for key, value in data.items():
            if value is not None:
                setattr(policy, key, value)
        await self.session.flush()
        return policy
