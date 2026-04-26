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
        rows = await self.repo.list(limit=1)
        return NodePolicyOut.model_validate(rows[0])

    async def update(self, data: NodePolicyUpdateIn) -> NodePolicyOut:
        rows = await self.repo.list(limit=1)
        policy = rows[0]
        payload = data.model_dump(exclude_unset=True, exclude_none=True)
        if payload:
            policy = await self.repo.update_by_id(policy.id, payload)
        return NodePolicyOut.model_validate(policy)


def get_node_policy_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> NodePolicyService:
    return NodePolicyService(session)
