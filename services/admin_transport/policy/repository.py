from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_transport.policy.model import TransportPolicy
from shared.database.base_repository import BaseRepository


class TransportPolicyRepository(BaseRepository[TransportPolicy]):
    def __init__(self, session: AsyncSession):
        super().__init__(TransportPolicy, session)

    async def get_current(self) -> TransportPolicy:
        rows = await self.list(limit=1)
        if rows:
            return rows[0]
        return await self.create({})

    async def update(self, *, data: dict) -> TransportPolicy:
        policy = await self.get_current()
        clean = {k: v for k, v in data.items() if v is not None}
        if not clean:
            return policy
        return await self.update_by_id(policy.id, clean)
