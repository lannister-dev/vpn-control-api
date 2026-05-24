from sqlalchemy.ext.asyncio import AsyncSession

from services.traffic.policy.models import TrafficPolicy
from shared.database.base_repository import BaseRepository


class TrafficPolicyRepository(BaseRepository[TrafficPolicy]):
    def __init__(self, session: AsyncSession):
        super().__init__(TrafficPolicy, session)
