from sqlalchemy.ext.asyncio import AsyncSession

from services.probe.policy.model import ProbePolicy
from shared.database.base_repository import BaseRepository


class ProbePolicyRepository(BaseRepository[ProbePolicy]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProbePolicy, session)

    async def get_current(self) -> ProbePolicy:
        rows = await self.list(limit=1)
        if rows:
            return rows[0]
        return await self.create({})

    async def update(self, *, data: dict) -> ProbePolicy:
        policy = await self.get_current()
        clean = {k: v for k, v in data.items() if v is not None}
        if not clean:
            return policy
        return await self.update_by_id(policy.id, clean)
