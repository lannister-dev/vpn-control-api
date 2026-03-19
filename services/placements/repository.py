from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy import and_, func, or_, select, update as sa_update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.placements.model import UserPlacement
from services.vpn.keys.models import VpnKey
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class UserPlacementRepository(BaseRepository[UserPlacement]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserPlacement, session)

    async def get_by_key_id(self, key_id: UUID) -> UserPlacement | None:
        rows = await self.list_by_key_id(key_id=key_id, active_only=True)
        if not rows:
            return None
        return rows[0]

    async def get_by_key_and_backend(
        self,
        *,
        key_id: UUID,
        backend_node_id: UUID,
        active_only: bool = True,
    ) -> UserPlacement | None:
        stmt = (
            select(self.model)
            .where(self.model.key_id == key_id)
            .where(self.model.backend_node_id == backend_node_id)
        )
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_key_id(
        self,
        *,
        key_id: UUID,
        active_only: bool = True,
        desired_state: str | None = None,
    ) -> list[UserPlacement]:
        stmt = select(self.model).where(self.model.key_id == key_id)
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        if desired_state is not None:
            stmt = stmt.where(self.model.desired_state == desired_state)
        stmt = stmt.order_by(self.model.updated_at.desc(), self.model.id.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

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

    async def count_desired_active_by_backend_node(self) -> dict[UUID, int]:
        stmt = (
            select(self.model.backend_node_id, func.count(self.model.id))
            .where(
                self.model.is_active.is_(True),
                self.model.desired_state == "active",
            )
            .group_by(self.model.backend_node_id)
        )
        res = await self.session.execute(stmt)
        return {row[0]: int(row[1]) for row in res.all()}

    async def list_transport_rows_by_placement_ids(
        self,
        *,
        placement_ids: list[UUID],
    ) -> list[tuple[UserPlacement, VpnKey]]:
        if not placement_ids:
            return []
        stmt = (
            select(self.model, VpnKey)
            .join(VpnKey, VpnKey.id == self.model.key_id)
            .where(self.model.id.in_(placement_ids))
            .where(self.model.is_active.is_(True))
            .where(VpnKey.is_active.is_(True))
        )
        result = await self.session.execute(stmt)
        return list(result.tuples().all())

    async def list_transport_rows_for_backend(
        self,
        *,
        backend_node_id: UUID,
    ) -> list[tuple[UserPlacement, VpnKey]]:
        stmt = (
            select(self.model, VpnKey)
            .join(VpnKey, VpnKey.id == self.model.key_id)
            .where(self.model.backend_node_id == backend_node_id)
            .where(self.model.is_active.is_(True))
            .where(VpnKey.is_active.is_(True))
            .order_by(self.model.updated_at.asc(), self.model.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.tuples().all())

    async def upsert_set_pending(
        self,
        *,
        key_id: UUID,
        backend_node_id: UUID,
        desired_state: str,
        sticky_until,
        last_migration_reason: str | None,
    ) -> UserPlacement:
        stmt = insert(self.model).values(
            key_id=key_id,
            backend_node_id=backend_node_id,
            desired_state=desired_state,
            applied_state="pending",
            op_version=1,
            applied_version=0,
            sticky_until=sticky_until,
            last_migration_reason=last_migration_reason,
            is_active=True,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_placement_key_backend",
            set_={
                "desired_state": desired_state,
                "applied_state": "pending",
                "op_version": self.model.op_version + 1,
                "sticky_until": sticky_until,
                "last_migration_reason": last_migration_reason,
                "is_active": True,
            },
        )
        await self.session.execute(stmt)
        row = await self.get_by_key_and_backend(
            key_id=key_id,
            backend_node_id=backend_node_id,
            active_only=True,
        )
        if row is None:
            raise RuntimeError("placement upsert failed to load placement row")
        return row

    async def set_desired_state_for_key(
        self,
        *,
        key_id: UUID,
        desired_state: str,
        last_migration_reason: str | None,
        updated_at: datetime,
        backend_node_ids: list[UUID] | None = None,
    ) -> int:
        stmt = (
            sa_update(self.model)
            .where(self.model.key_id == key_id)
            .where(self.model.is_active.is_(True))
            .where(
                or_(
                    self.model.desired_state != desired_state,
                    self.model.applied_state != "pending",
                )
            )
        )
        if backend_node_ids is not None:
            if not backend_node_ids:
                return 0
            stmt = stmt.where(self.model.backend_node_id.in_(backend_node_ids))

        result = await self.session.execute(
            stmt.values(
                desired_state=desired_state,
                applied_state="pending",
                op_version=self.model.op_version + 1,
                last_migration_reason=last_migration_reason,
                updated_at=updated_at,
            )
        )
        rowcount = result.rowcount
        if callable(rowcount):
            rowcount = rowcount()
        if rowcount is None or rowcount < 0:
            return 0
        return int(rowcount)

    async def apply_backend_report(
        self,
        *,
        placement_id: UUID,
        expected_op_version: int,
        applied_state: str,
        applied_version: int,
        updated_at: datetime,
        reporter_backend_id: UUID,
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
            .where(self.model.backend_node_id == reporter_backend_id)
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

        source_result = await self.session.execute(
            select(self.model).where(
                self.model.id.in_(placement_ids),
                self.model.is_active.is_(True),
            )
        )
        if not hasattr(source_result, "scalars"):
            rowcount = getattr(source_result, "rowcount", None)
            if callable(rowcount):
                rowcount = rowcount()
            if rowcount is None or rowcount < 0:
                return 0
            return int(rowcount)
        source_rows = list(source_result.scalars().all())
        if not source_rows:
            return 0

        key_ids = [row.key_id for row in source_rows]
        target_result = await self.session.execute(
            select(self.model).where(
                self.model.key_id.in_(key_ids),
                self.model.backend_node_id == target_backend_id,
            )
        )
        target_rows = list(target_result.scalars().all())
        target_by_key: dict[UUID, UserPlacement] = {
            row.key_id: row for row in target_rows
        }

        migrated = 0
        for source in source_rows:
            existing_target = target_by_key.get(source.key_id)
            if existing_target is None:
                await self.session.execute(
                    sa_update(self.model)
                    .where(self.model.id == source.id)
                    .values(
                        backend_node_id=target_backend_id,
                        applied_state="pending",
                        op_version=self.model.op_version + 1,
                        last_migration_reason=last_migration_reason,
                        updated_at=updated_at,
                    )
                )
                migrated += 1
                continue

            if existing_target.id == source.id:
                continue

            # Target already has placement for this key. Merge desired state there
            # and retire source row to avoid unique(key_id, backend_node_id) conflicts.
            await self.session.execute(
                sa_update(self.model)
                .where(self.model.id == existing_target.id)
                .values(
                    desired_state=source.desired_state,
                    applied_state="pending",
                    op_version=self.model.op_version + 1,
                    sticky_until=source.sticky_until,
                    last_migration_reason=last_migration_reason,
                    is_active=True,
                    updated_at=updated_at,
                )
            )
            await self.session.execute(
                sa_update(self.model)
                .where(self.model.id == source.id)
                .values(
                    is_active=False,
                    updated_at=updated_at,
                )
            )
            migrated += 1
        return migrated

    async def list_active_ids_for_key(
        self,
        *,
        key_id: UUID,
        desired_state: str,
        backend_node_ids: list[UUID] | None,
    ) -> list[UUID]:
        stmt = (
            select(self.model.id)
            .where(self.model.key_id == key_id)
            .where(self.model.is_active.is_(True))
            .where(self.model.desired_state == desired_state)
        )
        if backend_node_ids is not None:
            stmt = stmt.where(self.model.backend_node_id.in_(backend_node_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_ids_for_keys(
        self,
        *,
        key_ids: list[UUID],
        backend_node_id: UUID | None = None,
    ) -> list[UUID]:
        if not key_ids:
            return []
        stmt = (
            select(self.model.id)
            .where(self.model.key_id.in_(key_ids))
            .where(self.model.is_active.is_(True))
        )
        if backend_node_id is not None:
            stmt = stmt.where(self.model.backend_node_id == backend_node_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


def get_user_placement_repository(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> UserPlacementRepository:
    return UserPlacementRepository(session)
