from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.placements.repository import UserPlacementRepository


class _Result:
    def __init__(self, rowcount):
        self.rowcount = rowcount


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
async def test_apply_backend_reports_batch_returns_empty_for_no_reports(async_session):
    repo = UserPlacementRepository(async_session)

    out = await repo.apply_backend_reports_batch(
        reports=[],
        updated_at=datetime.now(timezone.utc),
        reporter_backend_id=uuid4(),
    )

    assert out == set()
    async_session.execute.assert_not_awaited()
