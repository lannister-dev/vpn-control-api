from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.policy.models import NodePolicy
from shared.database.base_repository import BaseRepository


class NodePolicyRepository(BaseRepository[NodePolicy]):
    def __init__(self, session: AsyncSession):
        super().__init__(NodePolicy, session)
