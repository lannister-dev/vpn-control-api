from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy import and_, func, or_, select, update as sa_update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.backend_peers.model import BackendPeer
from services.backend_peers.schemas import (
    BackendPeerAppliedState,
    BackendPeerInternalCreate,
    BackendPeerEnsureUpdate,
    BackendPeerStatus,
)
from services.nodes.models import VpnNode
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class BackendPeerRepository(BaseRepository[BackendPeer]):
    def __init__(self, session: AsyncSession):
        super().__init__(BackendPeer, session)

    async def get_by_pair(
            self,
            *,
            backend_node_id: UUID,
            gateway_node_id: UUID,
    ) -> BackendPeer | None:
        res = await self.session.execute(
            select(self.model).where(
                self.model.backend_node_id == backend_node_id,
                self.model.gateway_node_id == gateway_node_id,
            )
        )
        return res.scalar_one_or_none()

    async def list_active(
            self,
            *,
            backend_node_id: UUID | None = None,
            gateway_node_id: UUID | None = None,
            limit: int | None = None,
    ) -> list[BackendPeer]:
        stmt = select(self.model).where(self.model.is_active.is_(True))
        if backend_node_id is not None:
            stmt = stmt.where(self.model.backend_node_id == backend_node_id)
        if gateway_node_id is not None:
            stmt = stmt.where(self.model.gateway_node_id == gateway_node_id)
        stmt = stmt.order_by(self.model.updated_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count_active_by_backend_node(self) -> dict[UUID, int]:
        stmt = (
            select(self.model.backend_node_id, func.count(self.model.id))
            .where(self.model.is_active.is_(True))
            .group_by(self.model.backend_node_id)
        )
        res = await self.session.execute(stmt)
        return {row[0]: int(row[1]) for row in res.all()}

    async def count_active_by_gateway_node(self) -> dict[UUID, int]:
        stmt = (
            select(self.model.gateway_node_id, func.count(self.model.id))
            .where(self.model.is_active.is_(True))
            .group_by(self.model.gateway_node_id)
        )
        res = await self.session.execute(stmt)
        return {row[0]: int(row[1]) for row in res.all()}

    async def list_for_backend_page(
            self,
            *,
            backend_node_id: UUID,
            cursor: tuple[int, UUID] | None,
            limit: int,
    ) -> list[tuple[BackendPeer, VpnNode]]:
        stmt = (
            select(self.model, VpnNode)
            .join(VpnNode, VpnNode.id == self.model.gateway_node_id)
            .where(
                self.model.backend_node_id == backend_node_id,
                self.model.is_active.is_(True),
                VpnNode.is_active.is_(True),
            )
        )
        if cursor is not None:
            op, pid = cursor
            stmt = stmt.where(
                or_(
                    self.model.op_version > op,
                    and_(self.model.op_version == op, self.model.id > pid),
                )
            )
        stmt = stmt.order_by(self.model.op_version.asc(), self.model.id.asc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.tuples().all())

    async def list_for_gateway_page(
            self,
            *,
            gateway_node_id: UUID,
            cursor: tuple[int, UUID] | None,
            limit: int,
    ) -> list[tuple[BackendPeer, VpnNode]]:
        stmt = (
            select(self.model, VpnNode)
            .join(VpnNode, VpnNode.id == self.model.backend_node_id)
            .where(
                self.model.gateway_node_id == gateway_node_id,
                self.model.is_active.is_(True),
                VpnNode.is_active.is_(True),
            )
        )
        if cursor is not None:
            op, pid = cursor
            stmt = stmt.where(
                or_(
                    self.model.op_version > op,
                    and_(self.model.op_version == op, self.model.id > pid),
                )
            )
        stmt = stmt.order_by(self.model.op_version.asc(), self.model.id.asc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.tuples().all())

    async def upsert_set_pending(
            self,
            *,
            backend_node_id: UUID,
            gateway_node_id: UUID,
            status: BackendPeerStatus,
            internal_uuid: str | None = None,
    ) -> BackendPeer:
        provided_uuid = internal_uuid or str(uuid4())

        stmt = insert(self.model).values(
            backend_node_id=backend_node_id,
            gateway_node_id=gateway_node_id,
            internal_uuid=provided_uuid,
            status=status.value,
            applied_state=BackendPeerAppliedState.pending.value,
            op_version=1,
            applied_version=0,
            last_error=None,
            is_active=True,
        )
        on_conflict_update = {
            "status": status.value,
            "applied_state": BackendPeerAppliedState.pending.value,
            "op_version": self.model.op_version + 1,
            "last_error": None,
            "is_active": True,
        }
        if internal_uuid:
            on_conflict_update["internal_uuid"] = internal_uuid

        stmt = stmt.on_conflict_do_update(
            constraint="uq_backend_peer_pair",
            set_=on_conflict_update,
        )
        await self.session.execute(stmt)
        peer = await self.get_by_pair(
            backend_node_id=backend_node_id,
            gateway_node_id=gateway_node_id,
        )
        if not peer:
            raise RuntimeError("Failed to upsert backend peer")
        return peer

    async def ensure_active_pair(
            self,
            *,
            backend_node_id: UUID,
            gateway_node_id: UUID,
    ) -> BackendPeer:
        existing = await self.get_by_pair(
            backend_node_id=backend_node_id,
            gateway_node_id=gateway_node_id,
        )
        if not existing:
            create_data = BackendPeerInternalCreate(
                backend_node_id=backend_node_id,
                gateway_node_id=gateway_node_id,
                internal_uuid=str(uuid4()),
                status=BackendPeerStatus.active,
                applied_state=BackendPeerAppliedState.pending,
                op_version=1,
                applied_version=0,
                last_error=None,
                is_active=True,
            )
            try:
                return await self.create(create_data.model_dump())
            except IntegrityError:
                # Concurrent insert won the unique pair race. Re-read and continue idempotently.
                existing = await self.get_by_pair(
                    backend_node_id=backend_node_id,
                    gateway_node_id=gateway_node_id,
                )
                if not existing:
                    raise

        if existing.status == BackendPeerStatus.active.value and existing.is_active:
            return existing

        update_data = BackendPeerEnsureUpdate(
            status=BackendPeerStatus.active,
            applied_state=BackendPeerAppliedState.pending,
            op_version=existing.op_version + 1,
            is_active=True,
            last_error=None,
            updated_at=datetime.now(timezone.utc),
        )
        updated = await self.update_by_id(existing.id, update_data.model_dump())
        if not updated:
            raise RuntimeError("Failed to update backend peer")
        return updated

    async def apply_backend_report(
            self,
            *,
            peer_id: UUID,
            backend_node_id: UUID,
            expected_op_version: int,
            applied_state: str,
            applied_version: int,
            last_error: str | None,
            updated_at: datetime,
    ) -> int:
        result = await self.session.execute(
            sa_update(self.model)
            .where(self.model.id == peer_id)
            .where(self.model.backend_node_id == backend_node_id)
            .where(self.model.op_version == expected_op_version)
            .values(
                applied_state=applied_state,
                applied_version=applied_version,
                last_error=last_error,
                updated_at=updated_at,
            )
            .returning(self.model.id)
        )
        updated_ids = list(result.scalars().all())
        return len(updated_ids)


def get_backend_peer_repository(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> BackendPeerRepository:
    return BackendPeerRepository(session)
