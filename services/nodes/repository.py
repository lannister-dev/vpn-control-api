from fastapi import Depends
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode, NodeAgentState
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class VpnNodeRepository(BaseRepository[VpnNode]):
    def __init__(self, session: AsyncSession):
        super().__init__(VpnNode, session)

    async def get_by_internal_ip(self, source_ip: str) -> VpnNode | None:
        stmt = select(self.model).where(self.model.internal_wg_ip == source_ip)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def list_public(
            self,
            preferred_region: str | None = None,
    ) -> list[VpnNode]:
        stmt = select(self.model).where(self.model.region == preferred_region)
        result = await self.session.execute(stmt)

        return list(result.scalars().all())



# --------------------------------------------------------------

class NodeAgentStateRepository(BaseRepository[NodeAgentState]):
    def __init__(self, session: AsyncSession):
        super().__init__(NodeAgentState, session)
        self.session = session

    async def upsert(self, data: dict) -> None:
        stmt = insert(NodeAgentState).values(**data)

        stmt = stmt.on_conflict_do_update(
            index_elements=[NodeAgentState.node_id],
            set_={
                "agent_version": stmt.excluded.agent_version,
                "is_healthy": stmt.excluded.is_healthy,
                "last_seen_at": stmt.excluded.last_seen_at,
                "details": stmt.excluded.details,
                "updated_at": func.now(),
            },
        )

        await self.session.execute(stmt)
        await self.session.commit()
