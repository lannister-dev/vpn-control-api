from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.placements.schemas import PlacementAppliedState, PlacementApplyResultIn
from services.placements.service import PlacementApplyService


def _node():
    node = MagicMock()
    node.id = uuid4()
    return node


@pytest.mark.asyncio
async def test_apply_result_foreign_backend_returns_skipped_stale(async_session):
    """Foreign backend is now caught by WHERE clause returning 0 rows."""
    service = PlacementApplyService(async_session)
    service.placement_repository = AsyncMock()
    service.placement_repository.apply_backend_report.return_value = 0

    node = _node()

    result = await service.apply_result(
        node=node,
        placement_id=uuid4(),
        payload=PlacementApplyResultIn(
            op_version=1,
            applied_state=PlacementAppliedState.applied,
        ),
    )

    assert result == "skipped_stale"


@pytest.mark.asyncio
async def test_apply_result_skips_stale_version(async_session):
    """Stale op_version is caught by WHERE clause returning 0 rows."""
    service = PlacementApplyService(async_session)
    service.placement_repository = AsyncMock()
    service.placement_repository.apply_backend_report.return_value = 0

    node = _node()

    result = await service.apply_result(
        node=node,
        placement_id=uuid4(),
        payload=PlacementApplyResultIn(
            op_version=4,
            applied_state=PlacementAppliedState.applied,
        ),
    )

    assert result == "skipped_stale"


@pytest.mark.asyncio
async def test_apply_result_updates_applied(async_session):
    service = PlacementApplyService(async_session)
    service.placement_repository = AsyncMock()
    service.placement_repository.apply_backend_report.return_value = 1

    node = _node()
    placement_id = uuid4()

    result = await service.apply_result(
        node=node,
        placement_id=placement_id,
        payload=PlacementApplyResultIn(
            op_version=7,
            applied_state=PlacementAppliedState.applied,
        ),
    )

    assert result == "applied"
    service.placement_repository.apply_backend_report.assert_awaited_once_with(
        placement_id=placement_id,
        expected_op_version=7,
        applied_state=PlacementAppliedState.applied,
        applied_version=7,
        updated_at=ANY,
        reporter_backend_id=node.id,
    )


@pytest.mark.asyncio
async def test_apply_result_race_lost_is_stale(async_session):
    service = PlacementApplyService(async_session)
    service.placement_repository = AsyncMock()
    service.placement_repository.apply_backend_report.return_value = 0

    node = _node()

    result = await service.apply_result(
        node=node,
        placement_id=uuid4(),
        payload=PlacementApplyResultIn(
            op_version=4,
            applied_state=PlacementAppliedState.applied,
        ),
    )

    assert result == "skipped_stale"


@pytest.mark.asyncio
async def test_apply_result_idempotent_returns_skipped_stale(async_session):
    """Idempotent re-apply now returns skipped_stale (0 rows updated by WHERE clause)."""
    service = PlacementApplyService(async_session)
    service.placement_repository = AsyncMock()
    service.placement_repository.apply_backend_report.return_value = 0

    node = _node()

    result = await service.apply_result(
        node=node,
        placement_id=uuid4(),
        payload=PlacementApplyResultIn(
            op_version=9,
            applied_state=PlacementAppliedState.applied,
        ),
    )

    assert result == "skipped_stale"
