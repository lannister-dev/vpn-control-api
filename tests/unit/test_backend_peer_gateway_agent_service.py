from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.backend_peers.service import BackendPeerGatewayAgentService


def _node(*, role="gateway"):
    n = MagicMock()
    n.id = uuid4()
    n.role = role
    return n


def _peer(*, op_version=1):
    p = MagicMock()
    p.id = uuid4()
    p.backend_node_id = uuid4()
    p.gateway_node_id = uuid4()
    p.internal_uuid = str(uuid4())
    p.status = "active"
    p.applied_state = "pending"
    p.op_version = op_version
    p.applied_version = 0
    p.last_error = None
    return p


def _backend(*, role="backend", draining=False):
    b = MagicMock()
    b.internal_wg_ip = "10.0.1.10"
    b.xray_api_port = 10085
    b.role = role
    b.is_enabled = True
    b.is_draining = draining
    return b


@pytest.mark.asyncio
async def test_get_page_invalid_cursor(async_session):
    svc = BackendPeerGatewayAgentService(async_session)
    with pytest.raises(ValueError):
        await svc.get_page_for_gateway(node=_node(), cursor="bad", limit=10)


@pytest.mark.asyncio
async def test_get_page_marks_inactive_for_draining_backend(async_session):
    svc = BackendPeerGatewayAgentService(async_session)
    svc.peer_repository = AsyncMock()
    svc.peer_repository.list_for_gateway_page.return_value = [(_peer(), _backend(draining=True))]

    out = await svc.get_page_for_gateway(node=_node(role="gateway"), cursor=None, limit=10)
    assert len(out.items) == 1
    assert out.items[0].status.value == "inactive"


@pytest.mark.asyncio
async def test_get_page_rejects_non_gateway_role(async_session):
    svc = BackendPeerGatewayAgentService(async_session)
    svc.peer_repository = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await svc.get_page_for_gateway(node=_node(role="backend"), cursor=None, limit=10)
    assert exc.value.status_code == 403
