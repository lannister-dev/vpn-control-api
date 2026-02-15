from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.nodes.service import VpnNodeService
from services.vpn.keys.schemas import AssignmentReportIn, AssignmentAppliedState, AssignmentStatus


@pytest.mark.asyncio
async def test_report_assignment_updates_last_sync_at(monkeypatch, async_session):
    svc = VpnNodeService(async_session)
    svc.key_assignment_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    # Patch redis client used in the service module.
    from services.nodes import service as nodes_service_module
    redis_mock = MagicMock()
    redis_mock.client = AsyncMock()
    redis_mock.client.set = AsyncMock(return_value=True)
    redis_mock.client.delete = AsyncMock(return_value=1)
    monkeypatch.setattr(nodes_service_module, "redis_client", redis_mock)

    node = MagicMock()
    node.id = uuid4()

    assignment = MagicMock()
    assignment_id = uuid4()
    assignment.id = assignment_id
    assignment.node_id = node.id
    assignment.op_version = 1
    assignment.applied_state = AssignmentAppliedState.absent.value
    assignment.status = AssignmentStatus.pending.value
    assignment.last_error = None
    assignment.last_applied_at = None
    svc.key_assignment_repository.get_by_id = AsyncMock(return_value=assignment)
    svc.key_assignment_repository.update_by_id = AsyncMock()

    ts = datetime.now(timezone.utc)
    payload = AssignmentReportIn(
        op_version=1,
        applied_state=AssignmentAppliedState.present,
        status=AssignmentStatus.applied,
        last_error=None,
        last_applied_at=ts,
    )

    result = await svc.report_assignment(node=node, assignment_id=assignment_id, payload=payload)
    assert result == "applied"
    svc.node_agent_state_repository.update_by_node_id.assert_awaited_once()
