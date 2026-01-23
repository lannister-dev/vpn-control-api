from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode, NodeAgentState
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class VpnNodeRepository(BaseRepository[VpnNode]):
    def __init__(self, session: AsyncSession):
        super().__init__(VpnNode, session)


def get_vpn_node_repository(session: AsyncSession = Depends(AsyncDatabase.get_session)) -> VpnNodeRepository:
    return VpnNodeRepository(session)


# --------------------------------------------------------------

class NodeAgentStateRepository(BaseRepository[NodeAgentState]):
    def __init__(self, session: AsyncSession):
        super().__init__(NodeAgentState, session)


def get_node_agent_state_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> NodeAgentStateRepository:
    return NodeAgentStateRepository(session)
