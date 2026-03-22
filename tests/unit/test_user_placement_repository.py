from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.placements.repository import UserPlacementRepository


class _Result:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _TupleResult:
    def __init__(self, rows):
        self._rows = rows

    def tuples(self):
        return _Scalars(self._rows)


@pytest.mark.asyncio
async def test_list_active_ids_for_keys_returns_filtered_ids(async_session):
    repo = UserPlacementRepository(async_session)
    placement_ids = [uuid4(), uuid4()]
    async_session.execute = AsyncMock(return_value=_ScalarResult(placement_ids))

    out = await repo.list_active_ids_for_keys(
        key_ids=[uuid4(), uuid4()],
        backend_node_id=uuid4(),
    )

    assert out == placement_ids
    async_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_migrate_backend_returns_zero_for_empty_ids(async_session):
    repo = UserPlacementRepository(async_session)

    migrated, target_ids = await repo.bulk_migrate_backend(
        placement_ids=[],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )

    assert migrated == 0
    assert target_ids == []
    async_session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_migrate_backend_no_active_rows(async_session):
    repo = UserPlacementRepository(async_session)
    async_session.execute = AsyncMock(return_value=_ScalarResult([]))

    migrated, target_ids = await repo.bulk_migrate_backend(
        placement_ids=[uuid4(), uuid4()],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )

    assert migrated == 0
    assert target_ids == []


@pytest.mark.asyncio
async def test_bulk_migrate_backend_simple_move(async_session):
    """Simple move: no existing target → single bulk UPDATE RETURNING."""
    repo = UserPlacementRepository(async_session)

    s1 = MagicMock()
    s1.id = uuid4()
    s1.key_id = uuid4()
    s2 = MagicMock()
    s2.id = uuid4()
    s2.key_id = uuid4()

    async_session.execute = AsyncMock(
        side_effect=[
            _ScalarResult([s1, s2]),        # SELECT FOR UPDATE source
            _ScalarResult([]),              # SELECT FOR UPDATE target (no conflicts)
            _ScalarResult([s1.id, s2.id]),  # UPDATE ... RETURNING id
        ]
    )

    migrated, target_ids = await repo.bulk_migrate_backend(
        placement_ids=[s1.id, s2.id],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )

    assert migrated == 2
    assert target_ids == [s1.id, s2.id]
    assert async_session.execute.await_count == 3


@pytest.mark.asyncio
async def test_bulk_migrate_backend_merge_retires_source(async_session):
    """Multi-home merge: target already has placement for same key.

    Uses UPDATE ... FROM self-join to copy state, then retires source.
    """
    repo = UserPlacementRepository(async_session)

    key_id = uuid4()
    source = MagicMock()
    source.id = uuid4()
    source.key_id = key_id
    source.desired_state = "active"
    source.sticky_until = None

    target = MagicMock()
    target.id = uuid4()
    target.key_id = key_id
    target.is_active = False

    async_session.execute = AsyncMock(
        side_effect=[
            _ScalarResult([source]),       # SELECT FOR UPDATE source
            _ScalarResult([target]),       # SELECT FOR UPDATE target
            _ScalarResult([target.id]),    # UPDATE ... FROM src RETURNING id
            _Result(1),                    # UPDATE retire source
        ]
    )

    migrated, target_ids = await repo.bulk_migrate_backend(
        placement_ids=[source.id],
        target_backend_id=uuid4(),
        last_migration_reason="admin_manual",
        updated_at=datetime.now(timezone.utc),
    )

    assert migrated == 1
    assert target_ids == [target.id]
    assert async_session.execute.await_count == 4


@pytest.mark.asyncio
async def test_bulk_migrate_backend_mixed_move_and_merge(async_session):
    """Mix of simple moves and multi-home merges in a single call."""
    repo = UserPlacementRepository(async_session)

    key_a = uuid4()
    key_b = uuid4()

    # source A: simple move (no existing target)
    src_a = MagicMock()
    src_a.id = uuid4()
    src_a.key_id = key_a

    # source B: merge (target already has placement for key_b)
    src_b = MagicMock()
    src_b.id = uuid4()
    src_b.key_id = key_b
    src_b.desired_state = "active"
    src_b.sticky_until = None

    existing_b = MagicMock()
    existing_b.id = uuid4()
    existing_b.key_id = key_b

    async_session.execute = AsyncMock(
        side_effect=[
            _ScalarResult([src_a, src_b]),        # SELECT FOR UPDATE source
            _ScalarResult([existing_b]),           # SELECT FOR UPDATE target
            _ScalarResult([src_a.id]),             # bulk move RETURNING
            _ScalarResult([existing_b.id]),        # merge RETURNING
            _Result(1),                            # retire source_b
        ]
    )

    migrated, target_ids = await repo.bulk_migrate_backend(
        placement_ids=[src_a.id, src_b.id],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )

    assert migrated == 2
    assert target_ids == [src_a.id, existing_b.id]
    assert async_session.execute.await_count == 5
