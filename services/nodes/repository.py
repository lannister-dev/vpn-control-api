from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode, NodeAgentState, NodeAgentIdentity
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class VpnNodeRepository(BaseRepository[VpnNode]):
    def __init__(self, session: AsyncSession):
        super().__init__(VpnNode, session)

    async def get_by_internal_ip(self, source_ip: str) -> VpnNode | None:
        nodes = await self.list_by_internal_ip(source_ip=source_ip)
        if len(nodes) != 1:
            return None
        return nodes[0]

    async def list_by_internal_ip(self, source_ip: str) -> list[VpnNode]:
        stmt = (
            select(self.model)
            .where(self.model.internal_wg_ip == source_ip)
            .order_by(self.model.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_node_key(self, node_key: str) -> VpnNode | None:
        stmt = select(self.model).where(self.model.node_key == node_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_ids(self, node_ids: list[UUID]) -> list[VpnNode]:
        if not node_ids:
            return []
        stmt = select(self.model).where(self.model.id.in_(node_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def list_public(
            self,
            preferred_region: str | None = None,
            role: str | None = None,
    ) -> list[VpnNode]:
        stmt = select(self.model).where(self.model.is_active.is_(True))
        if role:
            stmt = stmt.where(self.model.role == role)
        if preferred_region:
            stmt = stmt.where(self.model.region == preferred_region)
        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def list_active_with_agent_state(self) -> list[tuple[VpnNode, NodeAgentState | None]]:
        stmt = (
            select(self.model, NodeAgentState)
            .outerjoin(NodeAgentState, NodeAgentState.node_id == self.model.id)
            .where(self.model.is_active.is_(True))
            .order_by(self.model.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.tuples().all())



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

    async def update_by_node_id(self, node_id: UUID, data: dict) -> None:
        await self.session.execute(
            update(NodeAgentState)
            .where(NodeAgentState.node_id == node_id)
            .values(**data)
        )

    async def touch_last_sync(self, *, node_id: UUID, at: datetime) -> None:
        """
        Update last_sync_at even if the node state row does not exist yet.
        This prevents losing sync timestamps on freshly bootstrapped agents.
        """
        stmt = insert(NodeAgentState).values(
            node_id=node_id,
            agent_version="unknown",
            is_healthy=True,
            last_seen_at=at,
            last_sync_at=at,
            details={},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[NodeAgentState.node_id],
            set_={
                "last_sync_at": at,
                "updated_at": func.now(),
            },
        )
        await self.session.execute(stmt)

    async def list_by_node_ids(self, node_ids: list[UUID]) -> list[NodeAgentState]:
        if not node_ids:
            return []
        stmt = select(NodeAgentState).where(NodeAgentState.node_id.in_(node_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class NodeAgentIdentityRepository(BaseRepository[NodeAgentIdentity]):
    def __init__(self, session: AsyncSession):
        super().__init__(NodeAgentIdentity, session)
        self.session = session

    async def get_by_node_and_instance(
        self,
        *,
        node_id: UUID,
        agent_instance_id: UUID,
    ) -> NodeAgentIdentity | None:
        stmt = (
            select(NodeAgentIdentity)
            .where(NodeAgentIdentity.node_id == node_id)
            .where(NodeAgentIdentity.agent_instance_id == agent_instance_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_token(
        self,
        *,
        node_id: UUID,
        agent_instance_id: UUID,
        token_hash: str,
    ) -> None:
        stmt = insert(NodeAgentIdentity).values(
            node_id=node_id,
            agent_instance_id=agent_instance_id,
            auth_token_hash=token_hash,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_node_agent_identity_node_agent",
            set_={
                "auth_token_hash": token_hash,
                "updated_at": func.now(),
            },
        )
        await self.session.execute(stmt)

    async def get_by_instance_and_token_hash(
        self,
        *,
        agent_instance_id: UUID,
        token_hash: str,
    ) -> NodeAgentIdentity | None:
        stmt = (
            select(NodeAgentIdentity)
            .where(NodeAgentIdentity.agent_instance_id == agent_instance_id)
            .where(NodeAgentIdentity.auth_token_hash == token_hash)
            .limit(2)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        if len(items) != 1:
            return None
        return items[0]
