from sqlalchemy.ext.asyncio import AsyncSession

from services.probe.policy.models import ProbePolicy
from shared.database.base_repository import BaseRepository


class ProbePolicyRepository(BaseRepository[ProbePolicy]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProbePolicy, session)
