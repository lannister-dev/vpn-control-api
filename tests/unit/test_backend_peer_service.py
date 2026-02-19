from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.backend_peers.schemas import BackendPeerStatus, BackendPeerUpsertIn
from services.backend_peers.service import BackendPeerService


def _node(*, role: str, public_domain: str = "gw.example.com", is_draining: bool = False):
    n = MagicMock()
    n.id = uuid4()
    n.role = role
    n.public_domain = public_domain
    n.is_active = True
    n.is_enabled = True
    n.is_draining = is_draining
    return n


def _peer(backend_node_id, gateway_node_id):
    p = MagicMock()
    p.id = uuid4()
    p.backend_node_id = backend_node_id
    p.gateway_node_id = gateway_node_id
    p.internal_uuid = str(uuid4())
    p.status = "active"
    p.applied_state = "pending"
    p.op_version = 1
    p.applied_version = 0
    p.last_error = None
    p.is_active = True
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    return p


@pytest.mark.asyncio
async def test_upsert_rejects_wrong_backend_role(async_session):
    svc = BackendPeerService(async_session)
    svc.node_repository = AsyncMock()
    svc.peer_repository = AsyncMock()

    backend = _node(role="gateway")
    gateway = _node(role="gateway")
    svc.node_repository.get_by_id = AsyncMock(side_effect=[backend, gateway])

    with pytest.raises(HTTPException) as exc:
        await svc.upsert(
            BackendPeerUpsertIn(
                backend_node_id=backend.id,
                gateway_node_id=gateway.id,
            )
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_upsert_success(async_session):
    svc = BackendPeerService(async_session)
    svc.node_repository = AsyncMock()
    svc.peer_repository = AsyncMock()

    backend = _node(role="backend")
    gateway = _node(role="gateway")
    peer = _peer(backend.id, gateway.id)

    svc.node_repository.get_by_id = AsyncMock(side_effect=[backend, gateway])
    svc.peer_repository.upsert_set_pending = AsyncMock(return_value=peer)

    out = await svc.upsert(
        BackendPeerUpsertIn(
            backend_node_id=backend.id,
            gateway_node_id=gateway.id,
            status=BackendPeerStatus.active,
        )
    )
    assert out.backend_node_id == backend.id
    assert out.gateway_node_id == gateway.id
