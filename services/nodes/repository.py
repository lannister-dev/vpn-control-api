from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from services.nodes.constants import ROLE_BACKEND, ROLE_ENTRY, ROLE_WHITELIST_ENTRY
from services.nodes.models import NodeAgentIdentity, NodeAgentState, VpnNode
from services.routing.entry.constants import ENTRY_HEARTBEAT_STALE_SEC
from shared.database.base_repository import BaseRepository


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

    async def list_used_wg_ips(self) -> set[str]:
        stmt = (
            select(self.model.internal_wg_ip)
            .where(self.model.internal_wg_ip.isnot(None))
            .where(self.model.internal_wg_ip != "")
        )
        result = await self.session.execute(stmt)
        return {row[0].strip() for row in result.all() if (row[0] or "").strip()}

    async def get_by_auth_token_hash(self, token_hash: str) -> VpnNode | None:
        stmt = select(self.model).where(self.model.auth_token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_ids(self, node_ids: list[UUID]) -> list[VpnNode]:
        if not node_ids:
            return []
        stmt = (
            select(self.model)
            .options(joinedload(self.model.agent_state))
            .where(self.model.id.in_(node_ids))
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    async def list_public(
            self,
            preferred_region: str | None = None,
    ) -> list[VpnNode]:
        stmt = select(self.model).where(self.model.is_active.is_(True))
        if preferred_region:
            stmt = stmt.where(self.model.region == preferred_region)
        result = await self.session.execute(stmt)

        return list(result.scalars().all())

    async def list_healthy_entries_by_zone(
            self,
    ) -> dict[str, list[VpnNode]]:
        from shared.utils.node_display import effective_zone

        fresh_after = datetime.now(timezone.utc) - timedelta(seconds=ENTRY_HEARTBEAT_STALE_SEC)
        stmt = (
            select(self.model)
            .outerjoin(NodeAgentState, NodeAgentState.node_id == self.model.id)
            .options(joinedload(self.model.agent_state))
            .where(
                self.model.role.in_((ROLE_ENTRY, ROLE_WHITELIST_ENTRY)),
                self.model.is_active.is_(True),
                self.model.is_enabled.is_(True),
                self.model.is_draining.is_(False),
                or_(
                    NodeAgentState.id.is_(None),
                    and_(
                        NodeAgentState.is_healthy.is_(True),
                        NodeAgentState.last_seen_at.is_not(None),
                        NodeAgentState.last_seen_at >= fresh_after,
                    ),
                ),
            )
            .order_by(self.model.id.asc())
        )
        result = await self.session.execute(stmt)
        grouped: dict[str, list[VpnNode]] = {}
        for node in result.unique().scalars().all():
            zone = effective_zone(
                explicit_zone=getattr(node, "zone", None),
                region=getattr(node, "region", None),
            )
            grouped.setdefault(zone, []).append(node)
        return grouped

    async def list_entries_with_dead_upstream(self) -> list[VpnNode]:
        """Entry/whitelist nodes pointing at an upstream that's disabled or draining."""
        upstream_alias = VpnNode.__table__.alias("upstream_node")
        stmt = (
            select(self.model)
            .join(
                upstream_alias,
                upstream_alias.c.id == self.model.upstream_node_id,
            )
            .where(
                self.model.role.in_((ROLE_ENTRY, ROLE_WHITELIST_ENTRY)),
                self.model.is_active.is_(True),
                self.model.is_enabled.is_(True),
                self.model.upstream_node_id.isnot(None),
                or_(
                    upstream_alias.c.is_enabled.is_(False),
                    upstream_alias.c.is_draining.is_(True),
                    upstream_alias.c.is_active.is_(False),
                ),
            )
            .order_by(self.model.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_live_backends(self) -> list[VpnNode]:
        """Backends fit to be picked as upstream: enabled, not draining, active."""
        stmt = (
            select(self.model)
            .where(
                self.model.role == ROLE_BACKEND,
                self.model.is_active.is_(True),
                self.model.is_enabled.is_(True),
                self.model.is_draining.is_(False),
            )
            .order_by(self.model.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def backend_tag_by_id(self) -> dict[str, str]:
        """Return {backend_node_id_str: "backend-<name>"} for all backend nodes."""
        stmt = select(self.model.id, self.model.name).where(self.model.role == ROLE_BACKEND)
        result = await self.session.execute(stmt)
        return {str(node_id): f"backend-{name}" for node_id, name in result.all() if name}

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
        previous_token_valid_until: datetime | None,
        full_resync_required: bool = True,
    ) -> None:
        now = datetime.now(timezone.utc)
        stmt = insert(NodeAgentIdentity).values(
            node_id=node_id,
            agent_instance_id=agent_instance_id,
            auth_token_hash=token_hash,
            prev_auth_token_hash=None,
            prev_auth_token_valid_until=None,
            full_resync_required=full_resync_required,
            last_bootstrap_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_node_agent_identity_node_agent",
            set_={
                "prev_auth_token_hash": NodeAgentIdentity.auth_token_hash,
                "prev_auth_token_valid_until": previous_token_valid_until,
                "auth_token_hash": token_hash,
                "full_resync_required": full_resync_required,
                "last_bootstrap_at": now,
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
            .where(
                or_(
                    NodeAgentIdentity.auth_token_hash == token_hash,
                    NodeAgentIdentity.prev_auth_token_hash == token_hash,
                )
            )
            .limit(2)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        if len(items) != 1:
            return None
        return items[0]

    async def clear_full_resync_required_for_node(self, *, node_id: UUID) -> None:
        await self.session.execute(
            update(NodeAgentIdentity)
            .where(NodeAgentIdentity.node_id == node_id)
            .values(
                full_resync_required=False,
                updated_at=func.now(),
            )
        )
