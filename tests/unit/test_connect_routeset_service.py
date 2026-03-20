from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.connect.schemas import ConnectRouteSetIn
from services.connect.service import ConnectService


def _redis():
    client = MagicMock()
    client.delete = AsyncMock(return_value=1)
    client.sadd = AsyncMock(return_value=1)
    client.expire = AsyncMock(return_value=True)
    return SimpleNamespace(client=client)


def _backend_node():
    n = MagicMock()
    n.id = uuid4()
    n.name = "be-fi-1"
    n.role = "backend"
    n.region = "fi"
    n.public_domain = "be-fi-1.example.com"
    n.reality_ip = "203.0.113.11"
    n.internal_wg_ip = "10.0.1.11"
    n.is_active = True
    n.is_enabled = True
    n.is_draining = False
    return n


def _route(*, node_id=None, name="be1-reality-google", weight=40, status="healthy"):
    r = MagicMock()
    r.id = uuid4()
    r.name = name
    r.node_id = node_id or uuid4()
    r.health_status = status
    r.effective_weight = weight
    return r


def _transport_profile(
        *,
        name: str = "reality-google",
        network: str = "tcp",
        security: str = "reality",
):
    tp = MagicMock()
    tp.id = uuid4()
    tp.name = name
    tp.network = network
    tp.security = security
    tp.reality_server_name = "www.google.com"
    tp.reality_public_key = "A" * 20
    tp.reality_short_id = "abcd1234"
    tp.tls_fingerprint = "chrome"
    tp.flow = "xtls-rprx-vision"
    tp.port = 443
    return tp


@pytest.mark.asyncio
async def test_connect_routeset_returns_routes(async_session):
    svc = ConnectService(async_session, _redis())
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()
    svc._select_backend = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend = _backend_node()
    placement = MagicMock(
        id=uuid4(),
        op_version=7,
        desired_state="active",
        backend_node_id=backend.id,
    )
    route_1 = _route(node_id=backend.id, name="be1-reality-google", weight=40)
    route_2 = _route(name="be2-reality-microsoft", weight=30)
    backend_2 = _backend_node()
    backend_2.id = route_2.node_id
    placement_2 = MagicMock(
        id=uuid4(),
        op_version=6,
        desired_state="active",
        backend_node_id=backend_2.id,
    )
    tp = _transport_profile()

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[placement, placement_2])
    svc.routing_service.select_nodes = AsyncMock(return_value=[backend, backend_2])
    svc.node_repository.get_by_id = AsyncMock(return_value=backend)
    svc.route_repository.list_resolved_active = AsyncMock(
        return_value=[(route_1, backend, tp), (route_2, backend_2, tp)]
    )
    svc._build_route_uri = MagicMock(side_effect=["vless://r1", "vless://r2"])

    out = await svc.connect_routeset(
        ConnectRouteSetIn(user_id=user_id, preferred_region="fi", max_routes=2)
    )

    assert out.key_id == key.id
    assert out.config_version == 7
    assert out.selection_strategy == "ordered_fallback"
    assert out.refresh_interval_sec == 60
    assert out.max_cache_age_sec == 300
    assert out.backoff_steps_sec == [2, 5, 10, 30, 60]
    assert [item.uri for item in out.routes] == ["vless://r1", "vless://r2"]
    svc.route_repository.list_resolved_active.assert_awaited_once_with(
        preferred_node_id=backend.id,
        preferred_region="fi",
        limit=10,
        backend_node_ids=sorted([backend.id, backend_2.id], key=str),
        node_seen_after=ANY,
    )


@pytest.mark.asyncio
async def test_connect_routeset_creates_placement_when_missing(async_session):
    svc = ConnectService(async_session, _redis())
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()
    svc._select_backend = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend = _backend_node()
    route = _route(node_id=backend.id)
    tp = _transport_profile()
    placement_new = MagicMock(
        id=uuid4(),
        op_version=3,
        desired_state="active",
        backend_node_id=backend.id,
    )

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[])
    svc.routing_service.select_nodes = AsyncMock(return_value=[backend])
    svc._select_backend = AsyncMock(return_value=backend)
    svc.placement_repository.upsert_set_pending = AsyncMock(return_value=placement_new)
    svc.route_repository.list_resolved_active = AsyncMock(return_value=[(route, backend, tp)])
    svc._build_route_uri = MagicMock(return_value="vless://route")

    out = await svc.connect_routeset(
        ConnectRouteSetIn(user_id=user_id, preferred_region="fi", max_routes=4)
    )

    assert out.key_id == key.id
    assert out.placement_id == placement_new.id
    assert out.placement_op_version == 3
    assert [item.uri for item in out.routes] == ["vless://route"]
    svc.placement_repository.upsert_set_pending.assert_awaited_once()
    svc.node_agent_transport.enqueue_for_placement_ids.assert_awaited_once_with([placement_new.id])
    kwargs = svc.placement_repository.upsert_set_pending.await_args.kwargs
    assert kwargs["backend_node_id"] == backend.id
    svc.route_repository.list_resolved_active.assert_awaited_once_with(
        preferred_node_id=backend.id,
        preferred_region="fi",
        limit=16,
        backend_node_ids=[backend.id],
        node_seen_after=ANY,
    )


@pytest.mark.asyncio
async def test_connect_routeset_returns_existing_target_placement_even_when_not_synced(async_session):
    svc = ConnectService(async_session, _redis())
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend = _backend_node()
    placement = MagicMock(
        id=uuid4(),
        op_version=7,
        applied_version=0,
        applied_state="pending",
        desired_state="active",
        backend_node_id=backend.id,
    )

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[placement])
    svc.routing_service.select_nodes = AsyncMock(return_value=[backend])
    route = _route(node_id=backend.id)
    tp = _transport_profile()
    svc.route_repository.list_resolved_active = AsyncMock(return_value=[(route, backend, tp)])
    svc._build_route_uri = MagicMock(return_value="vless://route")

    out = await svc.connect_routeset(
        ConnectRouteSetIn(user_id=user_id, preferred_region="fi", max_routes=1)
    )

    assert out.key_id == key.id
    assert out.placement_id == placement.id
    assert out.placement_op_version == 7
    assert [item.uri for item in out.routes] == ["vless://route"]
    svc.route_repository.list_resolved_active.assert_awaited_once_with(
        preferred_node_id=backend.id,
        preferred_region="fi",
        limit=10,
        backend_node_ids=[backend.id],
        node_seen_after=ANY,
    )


@pytest.mark.asyncio
async def test_connect_routeset_keeps_primary_and_fallback_mix(async_session):
    svc = ConnectService(async_session, _redis())
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend_primary = _backend_node()
    placement = MagicMock(
        id=uuid4(),
        op_version=9,
        desired_state="active",
        backend_node_id=backend_primary.id,
    )

    route_p1 = _route(node_id=backend_primary.id, name="be1-r1", weight=50)
    route_p2 = _route(node_id=backend_primary.id, name="be1-r2", weight=40)
    route_p3 = _route(node_id=backend_primary.id, name="be1-r3", weight=30)
    route_f1 = _route(name="be2-r1", weight=20)
    route_f2 = _route(name="be3-r1", weight=10)
    backend_f1 = _backend_node()
    backend_f1.id = route_f1.node_id
    backend_f2 = _backend_node()
    backend_f2.id = route_f2.node_id
    placement_f1 = MagicMock(
        id=uuid4(),
        op_version=8,
        desired_state="active",
        backend_node_id=backend_f1.id,
    )
    placement_f2 = MagicMock(
        id=uuid4(),
        op_version=7,
        desired_state="active",
        backend_node_id=backend_f2.id,
    )
    tp = _transport_profile()

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[placement, placement_f1, placement_f2])
    svc.routing_service.select_nodes = AsyncMock(
        return_value=[backend_primary, backend_f1, backend_f2]
    )
    svc.node_repository.get_by_id = AsyncMock(return_value=backend_primary)
    svc.route_repository.list_resolved_active = AsyncMock(
        return_value=[
            (route_p1, backend_primary, tp),
            (route_p2, backend_primary, tp),
            (route_p3, backend_primary, tp),
            (route_f1, backend_f1, tp),
            (route_f2, backend_f2, tp),
        ]
    )
    svc._build_route_uri = MagicMock(
        side_effect=["vless://p1", "vless://p2", "vless://p3", "vless://f1", "vless://f2"]
    )

    out = await svc.connect_routeset(
        ConnectRouteSetIn(user_id=user_id, preferred_region="fi", max_routes=4)
    )

    assert [item.uri for item in out.routes] == [
        "vless://p1",
        "vless://p2",
        "vless://f1",
        "vless://f2",
    ]
    svc.route_repository.list_resolved_active.assert_awaited_once_with(
        preferred_node_id=backend_primary.id,
        preferred_region="fi",
        limit=16,
        backend_node_ids=sorted([backend_primary.id, backend_f1.id, backend_f2.id], key=str),
        node_seen_after=ANY,
    )


@pytest.mark.asyncio
async def test_connect_routeset_includes_transport_insurance_when_available(async_session):
    svc = ConnectService(async_session, _redis())
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend_primary = _backend_node()
    placement = MagicMock(
        id=uuid4(),
        op_version=10,
        desired_state="active",
        backend_node_id=backend_primary.id,
    )

    route_p1 = _route(node_id=backend_primary.id, name="be1-r1", weight=50)
    route_p2 = _route(node_id=backend_primary.id, name="be1-r2", weight=45)
    route_f1 = _route(name="be2-r1", weight=40)
    route_f2 = _route(name="be3-grpc", weight=5)
    backend_f1 = _backend_node()
    backend_f1.id = route_f1.node_id
    backend_f2 = _backend_node()
    backend_f2.id = route_f2.node_id
    placement_f1 = MagicMock(
        id=uuid4(),
        op_version=9,
        desired_state="active",
        backend_node_id=backend_f1.id,
    )
    placement_f2 = MagicMock(
        id=uuid4(),
        op_version=8,
        desired_state="active",
        backend_node_id=backend_f2.id,
    )
    reality_tp = _transport_profile(name="reality-main", network="tcp", security="reality")
    grpc_tp = _transport_profile(name="grpc-insurance", network="grpc", security="tls")

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[placement, placement_f1, placement_f2])
    svc.routing_service.select_nodes = AsyncMock(
        return_value=[backend_primary, backend_f1, backend_f2]
    )
    svc.node_repository.get_by_id = AsyncMock(return_value=backend_primary)
    svc.route_repository.list_resolved_active = AsyncMock(
        return_value=[
            (route_p1, backend_primary, reality_tp),
            (route_p2, backend_primary, reality_tp),
            (route_f1, backend_f1, reality_tp),
            (route_f2, backend_f2, grpc_tp),
        ]
    )
    svc._build_route_uri = MagicMock(
        side_effect=["vless://p1", "vless://p2", "vless://f1", "vless://grpc"]
    )

    out = await svc.connect_routeset(
        ConnectRouteSetIn(user_id=user_id, preferred_region="fi", max_routes=3)
    )

    assert [item.uri for item in out.routes] == [
        "vless://p1",
        "vless://p2",
        "vless://grpc",
    ]


@pytest.mark.asyncio
async def test_connect_routeset_prefers_fallback_backend_diversity(async_session):
    svc = ConnectService(async_session, _redis())
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend_primary = _backend_node()
    placement = MagicMock(
        id=uuid4(),
        op_version=11,
        desired_state="active",
        backend_node_id=backend_primary.id,
    )

    route_p1 = _route(node_id=backend_primary.id, name="be1-r1", weight=50)
    route_p2 = _route(node_id=backend_primary.id, name="be1-r2", weight=45)
    route_f1 = _route(name="be2-r1", weight=40)
    route_f2 = _route(node_id=route_f1.node_id, name="be2-r2", weight=35)
    route_f3 = _route(name="be3-r1", weight=30)
    backend_f1 = _backend_node()
    backend_f1.id = route_f1.node_id
    backend_f2 = _backend_node()
    backend_f2.id = route_f3.node_id
    placement_f1 = MagicMock(
        id=uuid4(),
        op_version=10,
        desired_state="active",
        backend_node_id=backend_f1.id,
    )
    placement_f2 = MagicMock(
        id=uuid4(),
        op_version=9,
        desired_state="active",
        backend_node_id=backend_f2.id,
    )
    tp = _transport_profile(name="reality-main", network="tcp", security="reality")

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[placement, placement_f1, placement_f2])
    svc.routing_service.select_nodes = AsyncMock(
        return_value=[backend_primary, backend_f1, backend_f2]
    )
    svc.node_repository.get_by_id = AsyncMock(return_value=backend_primary)
    svc.route_repository.list_resolved_active = AsyncMock(
        return_value=[
            (route_p1, backend_primary, tp),
            (route_p2, backend_primary, tp),
            (route_f1, backend_f1, tp),
            (route_f2, backend_f1, tp),
            (route_f3, backend_f2, tp),
        ]
    )
    svc._build_route_uri = MagicMock(
        side_effect=["vless://p1", "vless://p2", "vless://f1", "vless://f2", "vless://f3"]
    )

    out = await svc.connect_routeset(
        ConnectRouteSetIn(user_id=user_id, preferred_region="fi", max_routes=4)
    )

    assert [item.uri for item in out.routes] == [
        "vless://p1",
        "vless://p2",
        "vless://f1",
        "vless://f3",
    ]


@pytest.mark.asyncio
async def test_connect_routeset_applies_refresh_policy_defaults_on_invalid_settings(async_session):
    svc = ConnectService(async_session, _redis())
    svc.settings = SimpleNamespace(
        routes=SimpleNamespace(
            connect_refresh_interval_sec=5,
            connect_max_cache_age_sec=1,
            connect_backoff_steps_sec=(0, -1),
        ),
        edge=SimpleNamespace(public_domain=""),
    )
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend = _backend_node()
    placement = MagicMock(
        id=uuid4(),
        op_version=4,
        desired_state="active",
        backend_node_id=backend.id,
    )
    route = _route(node_id=backend.id, name="be1-route", weight=50)
    tp = _transport_profile()

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[placement])
    svc.routing_service.select_nodes = AsyncMock(return_value=[backend])
    svc.node_repository.get_by_id = AsyncMock(return_value=backend)
    svc.route_repository.list_resolved_active = AsyncMock(return_value=[(route, backend, tp)])
    svc._build_route_uri = MagicMock(return_value="vless://route")

    out = await svc.connect_routeset(ConnectRouteSetIn(user_id=user_id, max_routes=1))

    assert out.refresh_interval_sec == 10
    assert out.max_cache_age_sec == 10
    assert out.backoff_steps_sec == [2, 5, 10, 30, 60]


@pytest.mark.asyncio
async def test_connect_routeset_raises_when_no_routes(async_session):
    svc = ConnectService(async_session, _redis())
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend = _backend_node()
    placement = MagicMock(
        id=uuid4(),
        op_version=5,
        desired_state="active",
        backend_node_id=backend.id,
    )

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[placement])
    svc.routing_service.select_nodes = AsyncMock(return_value=[backend])
    svc.node_repository.get_by_id = AsyncMock(return_value=backend)
    svc.route_repository.list_resolved_active = AsyncMock(return_value=[])

    with pytest.raises(HTTPException) as exc:
        await svc.connect_routeset(ConnectRouteSetIn(user_id=user_id))
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_connect_routeset_caches_allowed_routes_for_telemetry(async_session):
    redis = _redis()
    svc = ConnectService(async_session, redis)
    svc.user_repository = AsyncMock()
    svc.key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.routing_service = AsyncMock()

    user_id = uuid4()
    key = MagicMock(id=uuid4(), user_id=user_id, is_revoked=False, client_id=str(uuid4()))
    backend = _backend_node()
    placement = MagicMock(
        id=uuid4(),
        op_version=12,
        desired_state="active",
        backend_node_id=backend.id,
    )
    route = _route(node_id=backend.id, name="be1-route", weight=50)
    tp = _transport_profile()

    svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    svc.placement_repository.list_by_key_id = AsyncMock(return_value=[placement])
    svc.routing_service.select_nodes = AsyncMock(return_value=[backend])
    svc.node_repository.get_by_id = AsyncMock(return_value=backend)
    svc.route_repository.list_resolved_active = AsyncMock(return_value=[(route, backend, tp)])
    svc._build_route_uri = MagicMock(return_value="vless://route")

    out = await svc.connect_routeset(ConnectRouteSetIn(user_id=user_id, max_routes=1))

    assert out.routes[0].route_id == route.id
    redis.client.delete.assert_awaited_once()
    redis.client.sadd.assert_awaited_once()
    redis.client.expire.assert_awaited_once()
