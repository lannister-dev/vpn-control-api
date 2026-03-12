from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from services.placements.schemas import (
    PlacementAppliedState,
    PlacementBatchReportIn,
    PlacementBatchReportItemIn,
    PlacementReportIn,
)
from services.placements.service import PlacementAgentService


def _node(*, role="backend"):
    n = MagicMock()
    n.id = uuid4()
    n.role = role
    return n


def _placement(*, backend_node_id=None, op_version=1, applied_state="pending", applied_version=0):
    p = MagicMock()
    p.id = uuid4()
    p.key_id = uuid4()
    p.op_version = op_version
    p.applied_state = applied_state
    p.applied_version = applied_version
    p.desired_state = "active"
    p.backend_node_id = backend_node_id or uuid4()
    return p


def _key(*, revoked=False, valid_until=None):
    k = MagicMock()
    k.protocol = "vless"
    k.client_id = str(uuid4())
    k.transport = "ws"
    k.valid_until = valid_until
    k.is_revoked = revoked
    return k


def _backend():
    n = MagicMock()
    n.internal_wg_ip = "10.0.1.10"
    n.xray_api_port = 10085
    return n


@pytest.mark.asyncio
async def test_get_page_invalid_cursor(async_session):
    svc = PlacementAgentService(async_session)
    node = _node()
    with pytest.raises(ValueError):
        await svc.get_page_for_backend(node=node, cursor="bad", limit=10)


@pytest.mark.asyncio
async def test_get_page_effective_inactive_when_revoked(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id)
    key = _key(revoked=True)
    backend = _backend()
    svc.placement_repository.list_for_backend_with_keys_page.return_value = [(placement, key, backend)]

    out = await svc.get_page_for_backend(node=node, cursor=None, limit=10)

    assert len(out.items) == 1
    assert out.items[0].desired_state.value == "inactive"
    assert out.next_cursor is not None


@pytest.mark.asyncio
async def test_get_page_effective_inactive_when_expired(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id)
    key = _key(revoked=False, valid_until=datetime.now(timezone.utc) - timedelta(minutes=1))
    backend = _backend()
    svc.placement_repository.list_for_backend_with_keys_page.return_value = [(placement, key, backend)]

    out = await svc.get_page_for_backend(node=node, cursor=None, limit=10)
    assert out.items[0].desired_state.value == "inactive"


@pytest.mark.asyncio
async def test_get_page_keeps_transport_from_key(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id)
    key = _key()
    key.transport = "tcp"
    backend = _backend()
    svc.placement_repository.list_for_backend_with_keys_page.return_value = [(placement, key, backend)]

    out = await svc.get_page_for_backend(node=node, cursor=None, limit=10)

    assert len(out.items) == 1
    assert out.items[0].transport.value == "tcp"


@pytest.mark.asyncio
async def test_get_page_parses_updated_at_cursor(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id)
    placement.updated_at = datetime(2026, 3, 12, 18, 1, 40, tzinfo=timezone.utc)
    key = _key()
    backend = _backend()
    svc.placement_repository.list_for_backend_with_keys_page.return_value = [(placement, key, backend)]

    out = await svc.get_page_for_backend(
        node=node,
        cursor="1741802500000:550e8400-e29b-41d4-a716-446655440000",
        limit=10,
    )

    assert out.next_cursor == f"{int(placement.updated_at.timestamp() * 1000)}:{placement.id}"
    svc.placement_repository.list_for_backend_with_keys_page.assert_awaited_once_with(
        backend_node_id=node.id,
        cursor=(datetime.fromtimestamp(1741802500, tz=timezone.utc), UUID("550e8400-e29b-41d4-a716-446655440000")),
        limit=10,
    )


@pytest.mark.asyncio
async def test_report_forbidden_backend(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    other_backend_id = uuid4()
    placement = _placement(backend_node_id=other_backend_id)
    svc.placement_repository.get_by_id.return_value = placement

    with pytest.raises(HTTPException) as exc:
        await svc.report_for_backend(
            node=node,
            placement_id=placement.id,
            payload=PlacementReportIn(op_version=placement.op_version, applied_state=PlacementAppliedState.applied),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_report_skipped_stale(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id, op_version=5)
    svc.placement_repository.get_by_id.return_value = placement

    result = await svc.report_for_backend(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=4, applied_state=PlacementAppliedState.applied),
    )
    assert result == "skipped_stale"


@pytest.mark.asyncio
async def test_report_updates_applied(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id, op_version=7, applied_state="pending", applied_version=0)
    svc.placement_repository.get_by_id.return_value = placement
    svc.placement_repository.apply_backend_report.return_value = 1

    result = await svc.report_for_backend(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=7, applied_state=PlacementAppliedState.applied),
    )
    assert result == "applied"
    svc.placement_repository.apply_backend_report.assert_awaited_once_with(
        placement_id=placement.id,
        expected_op_version=7,
        applied_state=PlacementAppliedState.applied,
        applied_version=7,
        updated_at=ANY,
        reporter_backend_id=node.id,
    )


@pytest.mark.asyncio
async def test_report_applied_skipped_when_race_lost(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id, op_version=4, applied_state="pending", applied_version=0)
    svc.placement_repository.get_by_id.return_value = placement
    svc.placement_repository.apply_backend_report.return_value = 0

    result = await svc.report_for_backend(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=4, applied_state=PlacementAppliedState.applied),
    )
    assert result == "skipped_stale"


@pytest.mark.asyncio
async def test_report_skipped_idempotent(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node()
    placement = _placement(
        backend_node_id=node.id,
        op_version=9,
        applied_state=PlacementAppliedState.applied.value,
        applied_version=9,
    )
    svc.placement_repository.get_by_id.return_value = placement

    result = await svc.report_for_backend(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=9, applied_state=PlacementAppliedState.applied),
    )
    assert result == "skipped_idempotent"
    svc.placement_repository.apply_backend_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_batch_mixed_cases(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    placement_applied = _placement(backend_node_id=node.id, op_version=7, applied_state="pending", applied_version=0)
    placement_error = _placement(backend_node_id=node.id, op_version=8, applied_state="pending", applied_version=0)
    placement_idempotent = _placement(
        backend_node_id=node.id,
        op_version=9,
        applied_state=PlacementAppliedState.applied.value,
        applied_version=9,
    )
    svc.placement_repository.list_by_ids_for_backend.return_value = [
        placement_applied,
        placement_error,
        placement_idempotent,
    ]
    svc.placement_repository.apply_backend_reports_batch.return_value = {
        placement_applied.id,
        placement_error.id,
    }

    result = await svc.report_batch_for_backend(
        node=node,
        payload=PlacementBatchReportIn(
            items=[
                PlacementBatchReportItemIn(
                    placement_id=placement_applied.id,
                    op_version=7,
                    applied_state=PlacementAppliedState.applied,
                ),
                PlacementBatchReportItemIn(
                    placement_id=placement_error.id,
                    op_version=8,
                    applied_state=PlacementAppliedState.error,
                ),
                PlacementBatchReportItemIn(
                    placement_id=placement_idempotent.id,
                    op_version=9,
                    applied_state=PlacementAppliedState.applied,
                ),
                PlacementBatchReportItemIn(
                    placement_id=uuid4(),
                    op_version=10,
                    applied_state=PlacementAppliedState.applied,
                ),
            ]
        ),
    )

    assert [item.status for item in result.items] == [
        "applied",
        "error",
        "skipped_idempotent",
        "skipped_stale",
    ]
    svc.placement_repository.apply_backend_reports_batch.assert_awaited_once_with(
        reports=[
            (placement_applied.id, 7, "applied", 7),
            (placement_error.id, 8, "error", 8),
        ],
        updated_at=ANY,
        reporter_backend_id=node.id,
    )


@pytest.mark.asyncio
async def test_report_batch_marks_race_lost_updates_as_stale(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(backend_node_id=node.id, op_version=7, applied_state="pending", applied_version=0)
    svc.placement_repository.list_by_ids_for_backend.return_value = [placement]
    svc.placement_repository.apply_backend_reports_batch.return_value = set()

    result = await svc.report_batch_for_backend(
        node=node,
        payload=PlacementBatchReportIn(
            items=[
                PlacementBatchReportItemIn(
                    placement_id=placement.id,
                    op_version=7,
                    applied_state=PlacementAppliedState.applied,
                )
            ]
        ),
    )

    assert [item.status for item in result.items] == ["skipped_stale"]
