from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.backend_peers.schemas import BackendPeerAppliedState, BackendPeerReportIn
from services.backend_peers.service import BackendPeerAgentService


def _node(*, role="backend"):
    n = MagicMock()
    n.id = uuid4()
    n.role = role
    return n


def _peer(*, backend_node_id, op_version=1, applied_state="pending", applied_version=0):
    p = MagicMock()
    p.id = uuid4()
    p.backend_node_id = backend_node_id
    p.gateway_node_id = uuid4()
    p.internal_uuid = str(uuid4())
    p.status = "active"
    p.applied_state = applied_state
    p.op_version = op_version
    p.applied_version = applied_version
    p.last_error = None
    return p


def _gateway(*, role="gateway", draining=False):
    g = MagicMock()
    g.public_domain = "gw.example.com"
    g.role = role
    g.is_enabled = True
    g.is_draining = draining
    return g


@pytest.mark.asyncio
async def test_get_page_invalid_cursor(async_session):
    svc = BackendPeerAgentService(async_session)
    node = _node(role="backend")
    with pytest.raises(ValueError):
        await svc.get_page_for_backend(node=node, cursor="bad", limit=10)


@pytest.mark.asyncio
async def test_get_page_marks_inactive_for_draining_gateway(async_session):
    svc = BackendPeerAgentService(async_session)
    svc.peer_repository = AsyncMock()

    node = _node(role="backend")
    peer = _peer(backend_node_id=node.id)
    svc.peer_repository.list_for_backend_page.return_value = [(peer, _gateway(draining=True))]

    out = await svc.get_page_for_backend(node=node, cursor=None, limit=10)
    assert len(out.items) == 1
    assert out.items[0].status.value == "inactive"


@pytest.mark.asyncio
async def test_report_forbidden_backend(async_session):
    svc = BackendPeerAgentService(async_session)
    svc.peer_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node(role="backend")
    peer = _peer(backend_node_id=uuid4())
    svc.peer_repository.get_by_id.return_value = peer

    with pytest.raises(HTTPException) as exc:
        await svc.report_for_backend(
            node=node,
            peer_id=peer.id,
            payload=BackendPeerReportIn(op_version=1, applied_state=BackendPeerAppliedState.applied),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_report_updates_last_sync_on_applied(async_session):
    svc = BackendPeerAgentService(async_session)
    svc.peer_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node(role="backend")
    peer = _peer(backend_node_id=node.id, op_version=5, applied_state="pending", applied_version=0)
    svc.peer_repository.get_by_id.return_value = peer
    svc.peer_repository.apply_backend_report.return_value = 1

    result = await svc.report_for_backend(
        node=node,
        peer_id=peer.id,
        payload=BackendPeerReportIn(op_version=5, applied_state=BackendPeerAppliedState.applied),
    )
    assert result == "applied"
    svc.peer_repository.apply_backend_report.assert_awaited_once_with(
        peer_id=peer.id,
        backend_node_id=node.id,
        expected_op_version=5,
        applied_state=BackendPeerAppliedState.applied,
        applied_version=5,
        last_error=None,
        updated_at=ANY,
    )
    svc.node_agent_state_repository.touch_last_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_skipped_stale_when_atomic_update_fails(async_session):
    svc = BackendPeerAgentService(async_session)
    svc.peer_repository = AsyncMock()
    svc.node_agent_state_repository = AsyncMock()

    node = _node(role="backend")
    peer = _peer(backend_node_id=node.id, op_version=5, applied_state="pending", applied_version=0)
    svc.peer_repository.get_by_id.return_value = peer
    svc.peer_repository.apply_backend_report.return_value = 0

    result = await svc.report_for_backend(
        node=node,
        peer_id=peer.id,
        payload=BackendPeerReportIn(op_version=5, applied_state=BackendPeerAppliedState.applied),
    )
    assert result == "skipped_stale"
    svc.node_agent_state_repository.touch_last_sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_page_rejects_non_backend_role(async_session):
    svc = BackendPeerAgentService(async_session)
    svc.peer_repository = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await svc.get_page_for_backend(node=_node(role="gateway"), cursor=None, limit=10)
    assert exc.value.status_code == 403
