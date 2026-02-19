from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.placements.schemas import PlacementAppliedState, PlacementReportIn
from services.placements.service import PlacementAgentService


def _node(*, role="gateway"):
    n = MagicMock()
    n.id = uuid4()
    n.role = role
    return n


def _placement(*, gateway_node_id=None, op_version=1, applied_state="pending", applied_version=0):
    p = MagicMock()
    p.id = uuid4()
    p.key_id = uuid4()
    p.op_version = op_version
    p.applied_state = applied_state
    p.applied_version = applied_version
    p.desired_state = "active"
    p.backend_node_id = uuid4()
    p.gateway_node_id = gateway_node_id
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
        await svc.get_page_for_gateway(node=node, cursor="bad", limit=10)


@pytest.mark.asyncio
async def test_get_page_effective_inactive_when_revoked(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(gateway_node_id=node.id)
    key = _key(revoked=True)
    backend = _backend()
    svc.placement_repository.list_for_gateway_with_keys_page.return_value = [(placement, key, backend)]

    out = await svc.get_page_for_gateway(node=node, cursor=None, limit=10)

    assert len(out.items) == 1
    assert out.items[0].desired_state.value == "inactive"
    assert out.next_cursor is not None


@pytest.mark.asyncio
async def test_get_page_effective_inactive_when_expired(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    placement = _placement(gateway_node_id=node.id)
    key = _key(revoked=False, valid_until=datetime.now(timezone.utc) - timedelta(minutes=1))
    backend = _backend()
    svc.placement_repository.list_for_gateway_with_keys_page.return_value = [(placement, key, backend)]

    out = await svc.get_page_for_gateway(node=node, cursor=None, limit=10)
    assert out.items[0].desired_state.value == "inactive"


@pytest.mark.asyncio
async def test_report_forbidden_gateway(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()

    node = _node()
    other_node = _node()
    placement = _placement(gateway_node_id=other_node.id)
    svc.placement_repository.get_by_id.return_value = placement

    with pytest.raises(HTTPException) as exc:
        await svc.report_for_gateway(
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
    placement = _placement(gateway_node_id=node.id, op_version=5)
    svc.placement_repository.get_by_id.return_value = placement

    result = await svc.report_for_gateway(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=4, applied_state=PlacementAppliedState.applied),
    )
    assert result == "skipped_stale"
    svc.node_agent_state_repository.touch_last_sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_updates_applied(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node()
    placement = _placement(gateway_node_id=node.id, op_version=7, applied_state="pending", applied_version=0)
    svc.placement_repository.get_by_id.return_value = placement
    svc.placement_repository.apply_gateway_report.return_value = 1

    result = await svc.report_for_gateway(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=7, applied_state=PlacementAppliedState.applied),
    )
    assert result == "applied"
    svc.placement_repository.apply_gateway_report.assert_awaited_once_with(
        placement_id=placement.id,
        expected_op_version=7,
        applied_state=PlacementAppliedState.applied,
        applied_version=7,
        updated_at=ANY,
        reporter_gateway_id=node.id,
    )
    svc.node_agent_state_repository.touch_last_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_applied_on_unbound_placement(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node()
    placement = _placement(gateway_node_id=None, op_version=3, applied_state="pending", applied_version=0)
    svc.placement_repository.get_by_id.return_value = placement
    svc.placement_repository.apply_gateway_report.return_value = 1

    result = await svc.report_for_gateway(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=3, applied_state=PlacementAppliedState.applied),
    )
    assert result == "applied"
    svc.placement_repository.apply_gateway_report.assert_awaited_once_with(
        placement_id=placement.id,
        expected_op_version=3,
        applied_state=PlacementAppliedState.applied,
        applied_version=3,
        updated_at=ANY,
        reporter_gateway_id=node.id,
    )


@pytest.mark.asyncio
async def test_report_applied_skipped_when_bind_race_lost(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node()
    placement = _placement(gateway_node_id=None, op_version=4, applied_state="pending", applied_version=0)
    svc.placement_repository.get_by_id.return_value = placement
    svc.placement_repository.apply_gateway_report.return_value = 0

    result = await svc.report_for_gateway(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=4, applied_state=PlacementAppliedState.applied),
    )
    assert result == "skipped_stale"
    svc.node_agent_state_repository.touch_last_sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_skipped_idempotent(async_session):
    svc = PlacementAgentService(async_session)
    svc.placement_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node()
    placement = _placement(
        gateway_node_id=node.id,
        op_version=9,
        applied_state=PlacementAppliedState.applied.value,
        applied_version=9,
    )
    svc.placement_repository.get_by_id.return_value = placement

    result = await svc.report_for_gateway(
        node=node,
        placement_id=placement.id,
        payload=PlacementReportIn(op_version=9, applied_state=PlacementAppliedState.applied),
    )
    assert result == "skipped_idempotent"
    svc.placement_repository.apply_gateway_report.assert_not_awaited()
    svc.node_agent_state_repository.touch_last_sync.assert_not_awaited()
