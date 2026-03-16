from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.placements.schemas import PlacementAppliedState, PlacementApplyResultIn
from services.placements.service import PlacementApplyService


def _node():
    node = MagicMock()
    node.id = uuid4()
    return node


def _placement(*, backend_node_id=None, op_version=1, applied_state="pending", applied_version=0):
    placement = MagicMock()
    placement.id = uuid4()
    placement.op_version = op_version
    placement.applied_state = applied_state
    placement.applied_version = applied_version
    placement.backend_node_id = backend_node_id or uuid4()
    return placement


@pytest.mark.asyncio
async def test_apply_result_rejects_foreign_backend(async_session):
    service = PlacementApplyService(async_session)
    service.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=uuid4())
    service.placement_repository.get_by_id.return_value = placement

    with pytest.raises(HTTPException) as exc:
        await service.apply_result(
            node=node,
            placement_id=placement.id,
            payload=PlacementApplyResultIn(
                op_version=placement.op_version,
                applied_state=PlacementAppliedState.applied,
            ),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_apply_result_skips_stale_version(async_session):
    service = PlacementApplyService(async_session)
    service.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id, op_version=5)
    service.placement_repository.get_by_id.return_value = placement

    result = await service.apply_result(
        node=node,
        placement_id=placement.id,
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

    node = _node()
    placement = _placement(backend_node_id=node.id, op_version=7, applied_state="pending", applied_version=0)
    service.placement_repository.get_by_id.return_value = placement
    service.placement_repository.apply_backend_report.return_value = 1

    result = await service.apply_result(
        node=node,
        placement_id=placement.id,
        payload=PlacementApplyResultIn(
            op_version=7,
            applied_state=PlacementAppliedState.applied,
        ),
    )

    assert result == "applied"
    service.placement_repository.apply_backend_report.assert_awaited_once_with(
        placement_id=placement.id,
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

    node = _node()
    placement = _placement(backend_node_id=node.id, op_version=4, applied_state="pending", applied_version=0)
    service.placement_repository.get_by_id.return_value = placement
    service.placement_repository.apply_backend_report.return_value = 0

    result = await service.apply_result(
        node=node,
        placement_id=placement.id,
        payload=PlacementApplyResultIn(
            op_version=4,
            applied_state=PlacementAppliedState.applied,
        ),
    )

    assert result == "skipped_stale"


@pytest.mark.asyncio
async def test_apply_result_skips_idempotent(async_session):
    service = PlacementApplyService(async_session)
    service.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(
        backend_node_id=node.id,
        op_version=9,
        applied_state=PlacementAppliedState.applied.value,
        applied_version=9,
    )
    service.placement_repository.get_by_id.return_value = placement

    result = await service.apply_result(
        node=node,
        placement_id=placement.id,
        payload=PlacementApplyResultIn(
            op_version=9,
            applied_state=PlacementAppliedState.applied,
        ),
    )

    assert result == "skipped_idempotent"
    service.placement_repository.apply_backend_report.assert_not_awaited()
