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

    out = await repo.bulk_migrate_backend(
        placement_ids=[],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )

    assert out == 0
    async_session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_migrate_backend_reads_int_rowcount(async_session):
    repo = UserPlacementRepository(async_session)
    async_session.execute = AsyncMock(return_value=_Result(7))

    out = await repo.bulk_migrate_backend(
        placement_ids=[uuid4(), uuid4()],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )

    assert out == 7
    async_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_migrate_backend_reads_callable_rowcount(async_session):
    repo = UserPlacementRepository(async_session)
    async_session.execute = AsyncMock(return_value=_Result(lambda: 3))

    out = await repo.bulk_migrate_backend(
        placement_ids=[uuid4()],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )

    assert out == 3
    async_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_migrate_backend_handles_missing_or_negative_rowcount(async_session):
    repo = UserPlacementRepository(async_session)
    async_session.execute = AsyncMock(return_value=_Result(None))

    out_none = await repo.bulk_migrate_backend(
        placement_ids=[uuid4()],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )
    assert out_none == 0

    async_session.execute = AsyncMock(return_value=_Result(-1))
    out_negative = await repo.bulk_migrate_backend(
        placement_ids=[uuid4()],
        target_backend_id=uuid4(),
        last_migration_reason="test",
        updated_at=datetime.now(timezone.utc),
    )
    assert out_negative == 0


@pytest.mark.asyncio
async def test_bulk_migrate_backend_reuses_inactive_target_row(async_session):
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
            _ScalarResult([source]),
            _ScalarResult([target]),
            _Result(1),
            _Result(1),
        ]
    )

    out = await repo.bulk_migrate_backend(
        placement_ids=[source.id],
        target_backend_id=uuid4(),
        last_migration_reason="admin_manual",
        updated_at=datetime.now(timezone.utc),
    )

    assert out == 1
    assert async_session.execute.await_count == 4

    merge_stmt = async_session.execute.await_args_list[2].args[0]
    merge_params = merge_stmt.compile().params
    assert "desired_state" in merge_params
    assert "is_active" in merge_params
    assert "backend_node_id" not in merge_params

    retire_stmt = async_session.execute.await_args_list[3].args[0]
    retire_params = retire_stmt.compile().params
    assert retire_params["is_active"] is False
    assert "backend_node_id" not in retire_params
