from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.connect.schemas import ConnectIn
from services.connect.service import ConnectService
from shared.profiles.types import ProfileType


def _node(*, role="gateway"):
    n = MagicMock()
    n.id = uuid4()
    n.name = "gw-fi"
    n.role = role
    n.region = "fi"
    n.public_domain = "prod.example.com"
    n.internal_wg_ip = "10.0.1.10"
    n.is_active = True
    n.is_enabled = True
    n.is_draining = False
    return n


def _placement(*, key_id, backend_node_id, gateway_node_id, desired_state="active", op_version=2):
    p = MagicMock()
    p.id = uuid4()
    p.key_id = key_id
    p.backend_node_id = backend_node_id
    p.gateway_node_id = gateway_node_id
    p.desired_state = desired_state
    p.op_version = op_version
    return p


def _profile():
    p = MagicMock()
    p.type = ProfileType.ws_tls
    return p


@pytest.mark.asyncio
async def test_connect_user_not_found(async_session):
    svc = ConnectService(async_session)
    svc.user_repository = AsyncMock()
    svc.user_repository.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await svc.connect(ConnectIn(user_id=uuid4()))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_connect_existing_key_success(monkeypatch, async_session):
    svc = ConnectService(async_session)
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.backend_peer_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc._select_backend = AsyncMock()
    svc._select_gateway = AsyncMock()
    svc._ensure_backend_peers_for_all_gateways = AsyncMock()

    user_id = uuid4()
    key_id = uuid4()
    client_id = str(uuid4())
    gateway = _node()
    backend = _node()
    placement = MagicMock(id=uuid4(), op_version=2)
    key = MagicMock(
        id=key_id,
        user_id=user_id,
        is_revoked=False,
        transport="ws",
        client_id=client_id,
    )

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_by_id = AsyncMock(return_value=key)
    svc.placement_repository.get_by_key_id = AsyncMock(return_value=None)
    svc._select_backend.return_value = backend
    svc._select_gateway.return_value = gateway
    svc.backend_peer_repository.ensure_active_pair = AsyncMock()
    svc.placement_repository.upsert_set_pending = AsyncMock(return_value=placement)
    monkeypatch.setattr(svc, "_resolve_profile", lambda _: _profile())
    monkeypatch.setattr("services.connect.service.VlessUriBuilder.build", lambda **_: "vless://ok")

    out = await svc.connect(
        ConnectIn(
            user_id=user_id,
            key_id=key_id,
            profile_key="ws_tls_v1",
        )
    )

    assert out.key_id == key_id
    assert out.client_id == client_id
    assert out.uri == "vless://ok"
    svc.placement_repository.upsert_set_pending.assert_awaited_once()
    _, kwargs = svc.placement_repository.upsert_set_pending.await_args
    assert kwargs["gateway_node_id"] is None


@pytest.mark.asyncio
async def test_connect_creates_key_when_missing(monkeypatch, async_session):
    svc = ConnectService(async_session)
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.backend_peer_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc._select_backend = AsyncMock()
    svc._select_gateway = AsyncMock()
    svc._ensure_backend_peers_for_all_gateways = AsyncMock()

    user_id = uuid4()
    gateway = _node()
    backend = _node()
    placement = MagicMock(id=uuid4(), op_version=1)
    created_key = MagicMock(
        id=uuid4(),
        user_id=user_id,
        is_revoked=False,
        transport="ws",
        client_id=str(uuid4()),
        valid_until=datetime.now(timezone.utc),
    )

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=None)
    svc.key_repository.create = AsyncMock(return_value=created_key)
    svc.placement_repository.get_by_key_id = AsyncMock(return_value=None)
    svc._select_backend.return_value = backend
    svc._select_gateway.return_value = gateway
    svc.backend_peer_repository.ensure_active_pair = AsyncMock()
    svc.placement_repository.upsert_set_pending = AsyncMock(return_value=placement)
    monkeypatch.setattr(svc, "_resolve_profile", lambda _: _profile())
    monkeypatch.setattr("services.connect.service.VlessUriBuilder.build", lambda **_: "vless://new")

    out = await svc.connect(
        ConnectIn(
            user_id=user_id,
            profile_key="ws_tls_v1",
            traffic_limit_mb=500,
        )
    )

    assert out.key_id == created_key.id
    assert out.uri == "vless://new"
    svc.key_repository.create.assert_awaited_once()
    _, kwargs = svc.placement_repository.upsert_set_pending.await_args
    assert kwargs["gateway_node_id"] is None


@pytest.mark.asyncio
async def test_connect_reuses_existing_placement(monkeypatch, async_session):
    svc = ConnectService(async_session)
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.backend_peer_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc._select_backend = AsyncMock()
    svc._select_gateway = AsyncMock()
    svc._ensure_backend_peers_for_all_gateways = AsyncMock()

    user_id = uuid4()
    key_id = uuid4()
    client_id = str(uuid4())
    backend = _node(role="backend")
    gateway = _node(role="gateway")
    placement = _placement(
        key_id=key_id,
        backend_node_id=backend.id,
        gateway_node_id=gateway.id,
        desired_state="active",
        op_version=7,
    )
    key = MagicMock(
        id=key_id,
        user_id=user_id,
        is_revoked=False,
        transport="ws",
        client_id=client_id,
    )

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_by_id = AsyncMock(return_value=key)
    svc.placement_repository.get_by_key_id = AsyncMock(return_value=placement)
    svc.node_repository.get_by_id = AsyncMock(side_effect=[backend, gateway])
    svc.backend_peer_repository.ensure_active_pair = AsyncMock()
    svc.placement_repository.upsert_set_pending = AsyncMock()
    monkeypatch.setattr(svc, "_resolve_profile", lambda _: _profile())
    monkeypatch.setattr("services.connect.service.VlessUriBuilder.build", lambda **_: "vless://reuse")

    out = await svc.connect(
        ConnectIn(
            user_id=user_id,
            key_id=key_id,
            profile_key="ws_tls_v1",
        )
    )

    assert out.key_id == key_id
    assert out.placement_op_version == 7
    assert out.uri == "vless://reuse"
    svc._select_backend.assert_not_awaited()
    svc._select_gateway.assert_not_awaited()
    svc.placement_repository.upsert_set_pending.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_rebalances_when_existing_route_invalid(monkeypatch, async_session):
    svc = ConnectService(async_session)
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.backend_peer_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc._select_backend = AsyncMock()
    svc._select_gateway = AsyncMock()
    svc._ensure_backend_peers_for_all_gateways = AsyncMock()

    user_id = uuid4()
    key_id = uuid4()
    client_id = str(uuid4())
    bad_backend = _node(role="backend")
    bad_backend.is_draining = True
    gateway = _node(role="gateway")
    backend = _node(role="backend")
    placement_existing = _placement(
        key_id=key_id,
        backend_node_id=bad_backend.id,
        gateway_node_id=gateway.id,
        desired_state="active",
        op_version=2,
    )
    placement_new = _placement(
        key_id=key_id,
        backend_node_id=backend.id,
        gateway_node_id=gateway.id,
        desired_state="active",
        op_version=3,
    )
    key = MagicMock(
        id=key_id,
        user_id=user_id,
        is_revoked=False,
        transport="ws",
        client_id=client_id,
    )

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_by_id = AsyncMock(return_value=key)
    svc.placement_repository.get_by_key_id = AsyncMock(return_value=placement_existing)
    svc.node_repository.get_by_id = AsyncMock(return_value=bad_backend)
    svc._select_backend.return_value = backend
    svc._select_gateway.return_value = gateway
    svc.backend_peer_repository.ensure_active_pair = AsyncMock()
    svc.placement_repository.upsert_set_pending = AsyncMock(return_value=placement_new)
    monkeypatch.setattr(svc, "_resolve_profile", lambda _: _profile())
    monkeypatch.setattr("services.connect.service.VlessUriBuilder.build", lambda **_: "vless://rebalance")

    out = await svc.connect(
        ConnectIn(
            user_id=user_id,
            key_id=key_id,
            profile_key="ws_tls_v1",
        )
    )

    assert out.placement_op_version == 3
    assert out.uri == "vless://rebalance"
    svc.placement_repository.upsert_set_pending.assert_awaited_once()
    _, kwargs = svc.placement_repository.upsert_set_pending.await_args
    assert kwargs["last_migration_reason"] == "connect_rebalance"
    assert kwargs["gateway_node_id"] is None


@pytest.mark.asyncio
async def test_select_gateway_rejects_backend_role(async_session):
    svc = ConnectService(async_session)
    svc.node_repository = AsyncMock()

    gateway_id = uuid4()
    svc.node_repository.get_by_id = AsyncMock(return_value=_node(role="backend"))

    with pytest.raises(HTTPException) as exc:
        await svc._select_gateway(
            gateway_node_id=gateway_id,
            preferred_region="fi",
            fallback=_node(role="backend"),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_select_gateway_legacy_fallback_to_backend(async_session):
    svc = ConnectService(async_session)
    svc.node_repository = AsyncMock()
    svc.node_repository.list_public = AsyncMock(return_value=[])

    fallback = _node(role="backend")
    out = await svc._select_gateway(
        gateway_node_id=None,
        preferred_region="fi",
        fallback=fallback,
    )
    assert out == fallback
