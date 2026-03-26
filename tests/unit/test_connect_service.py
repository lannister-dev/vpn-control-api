from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.connect.service import ConnectService


def _redis():
    return SimpleNamespace(client=MagicMock())


def _node(*, role="backend", public_domain="prod.example.com", reality_ip=None):
    n = MagicMock()
    n.id = uuid4()
    n.name = "be-fi"
    n.role = role
    n.region = "fi"
    n.public_domain = public_domain
    n.reality_ip = public_domain if reality_ip is None else reality_ip
    n.internal_wg_ip = "10.0.1.10"
    n.is_active = True
    n.is_enabled = True
    n.is_draining = False
    return n


def _transport_profile(*, network="tcp", security="reality", port=443):
    tp = MagicMock()
    tp.id = uuid4()
    tp.name = "route-profile"
    tp.network = network
    tp.security = security
    tp.reality_server_name = "www.google.com"
    tp.reality_public_key = "A" * 20
    tp.reality_short_id = "abcd1234"
    tp.tls_fingerprint = "chrome"
    tp.grpc_service_name = "vl"
    tp.flow = "xtls-rprx-vision"
    tp.port = port
    return tp


@pytest.mark.asyncio
async def test_select_backend_skips_nodes_without_public_domain(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings.edge.public_domain = ""
    svc.routing_service = AsyncMock()
    svc.route_repository = AsyncMock()

    empty_domain = _node(public_domain="")
    with_domain = _node(public_domain="be-2.example.com")
    svc.routing_service.select_nodes = AsyncMock(return_value=[empty_domain, with_domain])
    svc.route_repository.list_backend_ids_with_entry_routes = AsyncMock(return_value=[])

    out = await svc._select_backend(preferred_region="fi")

    assert out.id == with_domain.id


@pytest.mark.asyncio
async def test_select_backend_uses_global_edge_domain(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings.edge.public_domain = "vpn.example.com"
    svc.routing_service = AsyncMock()
    svc.route_repository = AsyncMock()

    empty_domain = _node(public_domain="")
    svc.routing_service.select_nodes = AsyncMock(return_value=[empty_domain])
    svc.route_repository.list_backend_ids_with_entry_routes = AsyncMock(return_value=[])

    out = await svc._select_backend(preferred_region="fi")

    assert out.id == empty_domain.id


@pytest.mark.asyncio
async def test_build_route_uri_grpc_tls(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings.edge.public_domain = ""
    node = _node(public_domain="be-grpc.example.com")
    tp = _transport_profile(network="grpc", security="tls", port=443)

    uri = svc._build_route_uri(client_id="cid", backend_node=node, transport_profile=tp)

    assert uri is not None
    assert "type=grpc" in uri
    assert "security=tls" in uri
    assert "serviceName=vl" in uri


@pytest.mark.asyncio
async def test_build_route_uri_reality_uses_node_host_even_with_global_edge_domain(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings.edge.public_domain = "prod.example.com"
    node = _node(public_domain="1.2.3.4")
    tp = _transport_profile(network="tcp", security="reality", port=443)

    uri = svc._build_route_uri(client_id="cid", backend_node=node, transport_profile=tp)

    assert uri is not None
    assert "@1.2.3.4:" in uri
    assert "prod.example.com" not in uri


@pytest.mark.asyncio
async def test_build_route_uri_reality_prefers_reality_ip(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings.edge.public_domain = "prod.example.com"
    node = _node(public_domain="reality.example.com", reality_ip="203.0.113.10")
    tp = _transport_profile(network="tcp", security="reality", port=443)

    uri = svc._build_route_uri(client_id="cid", backend_node=node, transport_profile=tp)

    assert uri is not None
    assert "@203.0.113.10:" in uri
    assert "reality.example.com" not in uri


@pytest.mark.asyncio
async def test_build_route_uri_uses_entry_node_host(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings.edge.public_domain = "shared-edge.example.com"
    backend = _node(public_domain="", reality_ip=None)
    entry = _node(role="whitelist_entry", public_domain="entry.example.com", reality_ip="198.51.100.20")
    tp = _transport_profile(network="tcp", security="reality", port=443)

    uri = svc._build_route_uri(
        client_id="cid",
        backend_node=backend,
        public_node=entry,
        transport_profile=tp,
    )

    assert uri is not None
    assert "@entry.example.com:" in uri


@pytest.mark.asyncio
async def test_entry_route_makes_backend_eligible_without_public_host(async_session):
    svc = ConnectService(async_session, _redis())
    backend = _node(public_domain="", reality_ip=None)
    pending = MagicMock(
        id=uuid4(),
        key_id=uuid4(),
        backend_node_id=backend.id,
        desired_state="active",
        op_version=3,
        applied_version=0,
        applied_state="pending",
    )
    svc.placement_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    svc.routing_service = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.placement_repository.list_by_key_id.return_value = []
    svc.placement_repository.upsert_set_pending = AsyncMock(return_value=pending)
    svc.routing_service.select_nodes = AsyncMock(return_value=[backend])
    svc.route_repository.list_backend_ids_with_entry_routes = AsyncMock(return_value=[backend.id])

    preferred_backend_id, placement, allowed_backend_ids = await svc._ensure_backend_placements_for_key(
        key_id=uuid4(),
        preferred_region="fi",
        desired_replicas=1,
        key_transport="reality",
    )

    assert preferred_backend_id == backend.id
    assert placement.id == pending.id
    assert allowed_backend_ids == {backend.id}


@pytest.mark.asyncio
async def test_connect_returns_target_placement_even_when_not_synced(async_session):
    svc = ConnectService(async_session, _redis())
    backend = _node(public_domain="be.example.com", reality_ip="203.0.113.10")
    pending = MagicMock(
        id=uuid4(),
        key_id=uuid4(),
        backend_node_id=backend.id,
        desired_state="active",
        op_version=3,
        applied_version=0,
        applied_state="pending",
    )
    svc.placement_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    svc.routing_service = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.placement_repository.list_by_key_id.return_value = []
    svc.placement_repository.upsert_set_pending = AsyncMock(return_value=pending)
    svc.routing_service.select_nodes = AsyncMock(return_value=[backend])
    svc.route_repository.list_backend_ids_with_entry_routes = AsyncMock(return_value=[])

    preferred_backend_id, placement, allowed_backend_ids = await svc._ensure_backend_placements_for_key(
        key_id=uuid4(),
        preferred_region="fi",
        desired_replicas=1,
        key_transport="reality",
    )

    assert preferred_backend_id == backend.id
    assert placement.id == pending.id
    assert allowed_backend_ids == {backend.id}
