from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_transport.policy.model import TransportPolicy
from shared.database.base_repository import BaseRepository


class TransportPolicyRepository(BaseRepository[TransportPolicy]):
    def __init__(self, session: AsyncSession):
        super().__init__(TransportPolicy, session)
