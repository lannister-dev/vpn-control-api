from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.policy.repository import NodePolicyRepository
from services.nodes.policy.schemas import NodePolicyOut, NodePolicyUpdateIn
from shared.database.session import AsyncDatabase


class NodePolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NodePolicyRepository(session)

    async def get(self) -> NodePolicyOut:
        policy = await self.repo.get_current()
        await self.session.commit()
        return NodePolicyOut.model_validate(policy)

    async def update(self, data: NodePolicyUpdateIn) -> NodePolicyOut:
        payload = data.model_dump(exclude_unset=True)
        policy = await self.repo.update(data=payload)
        await self.session.commit()
        return NodePolicyOut.model_validate(policy)


def get_node_policy_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> NodePolicyService:
    return NodePolicyService(session)
