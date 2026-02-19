from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import Depends
from sqlalchemy.engine import CursorResult
from sqlalchemy import and_, func, or_, select, update as sa_update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode
from services.placements.model import UserPlacement
from services.vpn.keys.models import VpnKey
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class UserPlacementRepository(BaseRepository[UserPlacement]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserPlacement, session)

    async def get_by_key_id(self, key_id: UUID) -> UserPlacement | None:
        res = await self.session.execute(
            select(self.model).where(
                self.model.key_id == key_id,
                self.model.is_active.is_(True),
            )
        )
        return res.scalar_one_or_none()

    async def list_active(
            self,
            *,
            backend_node_id: UUID | None = None,
            limit: int | None = None,
    ) -> list[UserPlacement]:
        stmt = select(self.model).where(self.model.is_active.is_(True))
        if backend_node_id:
            stmt = stmt.where(self.model.backend_node_id == backend_node_id)
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
            .where(
                self.model.is_active.is_(True),
                self.model.gateway_node_id.is_not(None),
            )
            .group_by(self.model.gateway_node_id)
        )
        res = await self.session.execute(stmt)
        return {row[0]: int(row[1]) for row in res.all()}

    async def list_for_gateway_with_keys_page(
            self,
            *,
            gateway_node_id: UUID,
            cursor: tuple[int, UUID] | None,
            limit: int,
            include_unbound: bool = True,
    ) -> list[tuple[UserPlacement, VpnKey, VpnNode]]:
        stmt = (
            select(self.model, VpnKey, VpnNode)
            .join(VpnKey, VpnKey.id == self.model.key_id)
            .join(VpnNode, VpnNode.id == self.model.backend_node_id)
            .where(
                self.model.is_active.is_(True),
                VpnKey.is_active.is_(True),
                VpnNode.is_active.is_(True),
            )
        )
        if include_unbound:
            stmt = stmt.where(
                or_(
                    self.model.gateway_node_id == gateway_node_id,
                    self.model.gateway_node_id.is_(None),
                )
            )
        else:
            stmt = stmt.where(self.model.gateway_node_id == gateway_node_id)

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
        rows: list[tuple[UserPlacement, VpnKey, VpnNode]] = list(res.tuples().all())

        return rows

    async def upsert_set_pending(
            self,
            *,
            key_id: UUID,
            backend_node_id: UUID,
            gateway_node_id: UUID | None,
            desired_state: str,
            sticky_until,
            last_migration_reason: str | None,
    ) -> UserPlacement:
        stmt = insert(self.model).values(
            key_id=key_id,
            backend_node_id=backend_node_id,
            gateway_node_id=gateway_node_id,
            desired_state=desired_state,
            applied_state="pending",
            op_version=1,
            applied_version=0,
            sticky_until=sticky_until,
            last_migration_reason=last_migration_reason,
            is_active=True,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_placement_key_id",
            set_={
                "backend_node_id": backend_node_id,
                "gateway_node_id": gateway_node_id,
                "desired_state": desired_state,
                "applied_state": "pending",
                "op_version": self.model.op_version + 1,
                "sticky_until": sticky_until,
                "last_migration_reason": last_migration_reason,
                "is_active": True,
            },
        )
        await self.session.execute(stmt)
        return await self.get_by_key_id(key_id)

    async def apply_gateway_report(
            self,
            *,
            placement_id: UUID,
            expected_op_version: int,
            applied_state: str,
            applied_version: int,
            updated_at: datetime,
            reporter_gateway_id: UUID,
    ) -> int:
        values: dict = {
            "applied_state": applied_state,
            "applied_version": applied_version,
            "updated_at": updated_at,
        }
        result = await self.session.execute(
            sa_update(self.model)
            .where(self.model.id == placement_id)
            .where(self.model.op_version == expected_op_version)
            .where(
                or_(
                    self.model.gateway_node_id.is_(None),
                    self.model.gateway_node_id == reporter_gateway_id,
                )
            )
            .values(**values)
            .returning(self.model.id)
        )
        updated_ids = list(result.scalars().all())
        return len(updated_ids)

    async def bulk_migrate_backend(
            self,
            *,
            placement_ids: list[UUID],
            target_backend_id: UUID,
            last_migration_reason: str | None,
            updated_at: datetime,
    ) -> int:
        if not placement_ids:
            return 0

        result = cast(
            CursorResult,
            await self.session.execute(
                sa_update(self.model)
                .where(self.model.id.in_(placement_ids))
                .values(
                    backend_node_id=target_backend_id,
                    applied_state="pending",
                    op_version=self.model.op_version + 1,
                    last_migration_reason=last_migration_reason,
                    updated_at=updated_at,
                )
            ),
        )
        rowcount = result.rowcount
        if callable(rowcount):
            rowcount = rowcount()
        if rowcount is None or rowcount < 0:
            return 0
        return int(rowcount)


def get_user_placement_repository(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> UserPlacementRepository:
    return UserPlacementRepository(session)
