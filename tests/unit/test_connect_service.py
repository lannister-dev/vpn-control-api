from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.connect.service import ConnectService


def _redis():
    return SimpleNamespace(client=MagicMock())


def _node(*, role="backend", public_domain="prod.example.com"):
    n = MagicMock()
    n.id = uuid4()
    n.name = "be-fi"
    n.role = role
    n.region = "fi"
    n.public_domain = public_domain
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

    empty_domain = _node(public_domain="")
    with_domain = _node(public_domain="be-2.example.com")
    svc.routing_service.select_nodes = AsyncMock(return_value=[empty_domain, with_domain])

    out = await svc._select_backend(preferred_region="fi")

    assert out.id == with_domain.id


@pytest.mark.asyncio
async def test_select_backend_uses_global_edge_domain(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings.edge.public_domain = "vpn.example.com"
    svc.routing_service = AsyncMock()

    empty_domain = _node(public_domain="")
    svc.routing_service.select_nodes = AsyncMock(return_value=[empty_domain])

    out = await svc._select_backend(preferred_region="fi")

    assert out.id == empty_domain.id


@pytest.mark.asyncio
async def test_build_route_uri_grpc_tls(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings.edge.public_domain = ""
    node = _node(public_domain="be-grpc.example.com")
    tp = _transport_profile(network="grpc", security="tls", port=443)

    uri = svc._build_route_uri(client_id="cid", node=node, transport_profile=tp)

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

    uri = svc._build_route_uri(client_id="cid", node=node, transport_profile=tp)

    assert uri is not None
    assert "@1.2.3.4:" in uri
    assert "prod.example.com" not in uri
