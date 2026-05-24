from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin.transport.policy.repository import TransportPolicyRepository
from services.admin.transport.policy.schemas import TransportPolicyOut, TransportPolicyUpdateIn
from shared.database.session import AsyncDatabase


class TransportPolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TransportPolicyRepository(session)

    async def get(self) -> TransportPolicyOut:
        rows = await self.repo.list(limit=1)
        return TransportPolicyOut.model_validate(rows[0])

    async def update(self, data: TransportPolicyUpdateIn) -> TransportPolicyOut:
        rows = await self.repo.list(limit=1)
        policy = rows[0]
        payload = data.model_dump(exclude_unset=True, exclude_none=True)
        if payload:
            policy = await self.repo.update_by_id(policy.id, payload)
        return TransportPolicyOut.model_validate(policy)


def get_transport_policy_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> TransportPolicyService:
    return TransportPolicyService(session)
