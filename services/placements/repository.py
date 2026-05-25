from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from services.placements.models import UserPlacement
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
                "updated_at": func.now(),
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

    async def set_pending_for_backend(
        self,
        *,
        backend_node_id: UUID,
        last_migration_reason: str | None,
        updated_at: datetime,
    ) -> list[UUID]:
        result = await self.session.execute(
            sa_update(self.model)
            .where(
                self.model.backend_node_id == backend_node_id,
                self.model.is_active.is_(True),
            )
            .values(
                applied_state="pending",
                op_version=self.model.op_version + 1,
                last_migration_reason=last_migration_reason,
                updated_at=updated_at,
            )
            .returning(self.model.id)
        )
        return list(result.scalars().all())

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

    async def bulk_apply_backend_report(
        self,
        items: list[dict],
    ) -> set[UUID]:
        """Bulk update placements. Each item: {id, op_version, backend_node_id, applied_state, applied_version, updated_at}.
        Returns set of placement IDs that were actually updated."""
        if not items:
            return set()
        # Group by applied_state to batch updates
        from collections import defaultdict
        by_state: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            by_state[item["applied_state"]].append(item)

        updated: set[UUID] = set()
        for applied_state, group in by_state.items():
            ids_versions = [
                (item["id"], item["op_version"], item["backend_node_id"])
                for item in group
            ]
            result = await self.session.execute(
                sa_update(self.model)
                .where(
                    func.row(self.model.id, self.model.op_version, self.model.backend_node_id)
                    .in_(ids_versions)
                )
                .values(
                    applied_state=applied_state,
                    applied_version=self.model.op_version,
                    updated_at=group[0]["updated_at"],
                )
                .returning(self.model.id)
            )
            updated.update(result.scalars().all())
        return updated

    async def bulk_migrate_backend(
        self,
        *,
        placement_ids: list[UUID],
        target_backend_id: UUID,
        last_migration_reason: str | None,
        updated_at: datetime,
    ) -> tuple[int, list[UUID]]:
        """Migrate placements to a new backend node.

        Returns (migrated_count, target_placement_ids) where
        target_placement_ids are the IDs that need outbox entries on the
        target node.  Uses SELECT FOR UPDATE to prevent concurrent
        migration of the same rows.

        SQL complexity: O(1) statements regardless of placement count
        (2 SELECTs + up to 3 UPDATEs).
        """
        if not placement_ids:
            return 0, []

        # Lock source rows to prevent concurrent migration
        source_rows = list(
            (await self.session.execute(
                select(self.model)
                .where(
                    self.model.id.in_(placement_ids),
                    self.model.is_active.is_(True),
                )
                .with_for_update()
            )).scalars().all()
        )
        if not source_rows:
            return 0, []

        # Lock any existing target rows (same key already on target node)
        key_ids = [r.key_id for r in source_rows]
        target_by_key: dict[UUID, UserPlacement] = {
            r.key_id: r
            for r in (await self.session.execute(
                select(self.model)
                .where(
                    self.model.key_id.in_(key_ids),
                    self.model.backend_node_id == target_backend_id,
                )
                .with_for_update()
            )).scalars().all()
        }

        # Partition into simple moves vs multi-home merges
        simple_move_ids: list[UUID] = []
        merge_source_ids: list[UUID] = []

        for src in source_rows:
            existing = target_by_key.get(src.key_id)
            if existing is None:
                simple_move_ids.append(src.id)
            elif existing.id != src.id:
                merge_source_ids.append(src.id)

        target_ids: list[UUID] = []
        migrated = 0

        # Bulk UPDATE: move placements to target node (single statement)
        if simple_move_ids:
            result = await self.session.execute(
                sa_update(self.model)
                .where(self.model.id.in_(simple_move_ids))
                .values(
                    backend_node_id=target_backend_id,
                    applied_state="pending",
                    op_version=self.model.op_version + 1,
                    last_migration_reason=last_migration_reason,
                    updated_at=updated_at,
                )
                .returning(self.model.id)
            )
            moved = list(result.scalars().all())
            target_ids.extend(moved)
            migrated += len(moved)

        # Bulk merge: UPDATE ... FROM self-join to copy desired_state
        # and sticky_until from source rows into existing target rows,
        # then retire the sources.
        if merge_source_ids:
            src = self.model.__table__.alias("src")
            merge_result = await self.session.execute(
                sa_update(self.model)
                .where(
                    self.model.backend_node_id == target_backend_id,
                    self.model.key_id == src.c.key_id,
                    src.c.id.in_(merge_source_ids),
                )
                .values(
                    desired_state=src.c.desired_state,
                    applied_state="pending",
                    op_version=self.model.op_version + 1,
                    sticky_until=src.c.sticky_until,
                    last_migration_reason=last_migration_reason,
                    is_active=True,
                    updated_at=updated_at,
                )
                .returning(self.model.id)
            )
            merged = list(merge_result.scalars().all())
            target_ids.extend(merged)
            migrated += len(merged)

            # Retire source rows
            await self.session.execute(
                sa_update(self.model)
                .where(self.model.id.in_(merge_source_ids))
                .values(is_active=False, updated_at=updated_at)
            )

        return migrated, target_ids

    async def bulk_set_desired_state_for_keys(
        self,
        *,
        key_ids: list[UUID],
        desired_state: str,
        last_migration_reason: str | None,
        updated_at: datetime,
    ) -> list[UUID]:
        if not key_ids:
            return []
        stmt = (
            sa_update(self.model)
            .where(self.model.key_id.in_(key_ids))
            .where(self.model.is_active.is_(True))
            .where(
                or_(
                    self.model.desired_state != desired_state,
                    self.model.applied_state != "pending",
                )
            )
            .values(
                desired_state=desired_state,
                applied_state="pending",
                op_version=self.model.op_version + 1,
                last_migration_reason=last_migration_reason,
                updated_at=updated_at,
            )
            .returning(self.model.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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


    async def map_active_backend_nodes_by_key(
        self,
        *,
        key_ids: list[UUID],
    ) -> dict[UUID, set[UUID]]:
        """Return {key_id: {backend_node_id, ...}} for active placements."""
        if not key_ids:
            return {}
        stmt = (
            select(self.model.key_id, self.model.backend_node_id)
            .where(
                self.model.key_id.in_(key_ids),
                self.model.is_active.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        out: dict[UUID, set[UUID]] = {}
        for key_id, node_id in result.all():
            out.setdefault(key_id, set()).add(node_id)
        return out

    async def find_missing_placements(
        self,
        *,
        healthy_node_ids: list[UUID],
        batch_size: int = 200,
    ) -> list[tuple[UUID, UUID]]:
        """Find (key_id, node_id) pairs where an active key is missing
        a placement on a healthy node."""
        if not healthy_node_ids:
            return []

        active_keys = (
            select(self.model.key_id)
            .where(
                self.model.is_active.is_(True),
                self.model.desired_state == "active",
            )
            .distinct()
            .subquery("active_keys")
        )

        nodes_cte = select(
            func.unnest(cast(healthy_node_ids, ARRAY(PG_UUID))).label("id")
        ).subquery("healthy_nodes")

        cross = (
            select(
                active_keys.c.key_id.label("key_id"),
                nodes_cte.c.id.label("node_id"),
            )
            .subquery("expected")
        )

        existing = self.model.__table__.alias("existing")
        stmt = (
            select(cross.c.key_id, cross.c.node_id)
            .outerjoin(
                existing,
                and_(
                    existing.c.key_id == cross.c.key_id,
                    existing.c.backend_node_id == cross.c.node_id,
                    existing.c.is_active.is_(True),
                ),
            )
            .where(existing.c.id.is_(None))
            .limit(batch_size)
        )

        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def bulk_upsert_set_pending(
        self,
        *,
        pairs: list[tuple[UUID, UUID]],
        desired_state: str = "active",
        last_migration_reason: str | None = None,
    ) -> list[UUID]:
        """Bulk upsert placements for (key_id, backend_node_id) pairs.
        Returns list of created/updated placement IDs."""
        if not pairs:
            return []

        values_list = [
            {
                "key_id": key_id,
                "backend_node_id": node_id,
                "desired_state": desired_state,
                "applied_state": "pending",
                "op_version": 1,
                "applied_version": 0,
                "sticky_until": None,
                "last_migration_reason": last_migration_reason,
                "is_active": True,
            }
            for key_id, node_id in pairs
        ]

        stmt = insert(self.model).values(values_list)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_placement_key_backend",
            set_={
                "desired_state": desired_state,
                "applied_state": "pending",
                "op_version": self.model.op_version + 1,
                "sticky_until": None,
                "last_migration_reason": last_migration_reason,
                "is_active": True,
                "updated_at": func.now(),
            },
        ).returning(self.model.id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())


def get_user_placement_repository(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> UserPlacementRepository:
    return UserPlacementRepository(session)
