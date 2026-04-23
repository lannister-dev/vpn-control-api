from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_transport.policy.repository import TransportPolicyRepository
from services.admin_transport.policy.schemas import TransportPolicyOut, TransportPolicyUpdateIn
from shared.database.session import AsyncDatabase


class TransportPolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TransportPolicyRepository(session)

    async def get(self) -> TransportPolicyOut:
        policy = await self.repo.get_current()
        await self.session.commit()
        return TransportPolicyOut.model_validate(policy)

    async def update(self, data: TransportPolicyUpdateIn) -> TransportPolicyOut:
        payload = data.model_dump(exclude_unset=True)
        policy = await self.repo.update(data=payload)
        await self.session.commit()
        return TransportPolicyOut.model_validate(policy)


def get_transport_policy_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> TransportPolicyService:
    return TransportPolicyService(session)
