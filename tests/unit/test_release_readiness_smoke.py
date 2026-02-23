from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.connect.schemas import ConnectRouteSetIn, ConnectTelemetryEvent, ConnectTelemetryIn
from services.connect.service import ConnectService
from services.connect.telemetry_service import ConnectTelemetryService
from services.routes.schemas import RouteHealthAction, RouteHealthUpdateIn
from services.routes.service import RouteService


def _redis_wrapper() -> SimpleNamespace:
    client = AsyncMock()
    client.delete = AsyncMock(return_value=1)
    client.sadd = AsyncMock(return_value=1)
    client.expire = AsyncMock(return_value=True)
    return SimpleNamespace(client=client)


def _backend_node():
    node = MagicMock()
    node.id = uuid4()
    node.name = "be-fi-1"
    node.role = "backend"
    node.region = "fi"
    node.public_domain = "be-fi-1.example.com"
    node.internal_wg_ip = "10.0.1.11"
    node.is_active = True
    node.is_enabled = True
    node.is_draining = False
    return node


def _transport_profile():
    tp = MagicMock()
    tp.id = uuid4()
    tp.name = "reality-google"
    tp.network = "tcp"
    tp.security = "reality"
    tp.reality_server_name = "www.google.com"
    tp.reality_public_key = "A" * 20
    tp.reality_short_id = "abcd1234"
    tp.tls_fingerprint = "chrome"
    tp.flow = "xtls-rprx-vision"
    tp.port = 443
    return tp


def _route_entity(*, node_id, transport_profile_id):
    now = datetime.now(timezone.utc)
    route = MagicMock()
    route.id = uuid4()
    route.name = "be1-reality-google"
    route.node_id = node_id
    route.transport_profile_id = transport_profile_id
    route.health_status = "healthy"
    route.base_weight = 50
    route.effective_weight = 50
    route.cooldown_until = None
    route.warmup_stage = None
    route.warmup_started_at = None
    route.is_active = True
    route.created_at = now
    route.updated_at = now
    return route


def _normalize_value(value):
    if isinstance(value, Enum):
        return value.value
    return value


@pytest.mark.asyncio
async def test_release_smoke_connect_telemetry_block_warmup_recovery(async_session):
    backend = _backend_node()
    tp = _transport_profile()
    route = _route_entity(node_id=backend.id, transport_profile_id=tp.id)
    user_id = uuid4()
    key_id = uuid4()
    key = MagicMock(
        id=key_id,
        user_id=user_id,
        is_revoked=False,
        client_id=str(uuid4()),
        is_active=True,
        valid_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    placement = MagicMock(
        id=uuid4(),
        op_version=7,
        desired_state="active",
        backend_node_id=backend.id,
    )

    connect_svc = ConnectService(async_session, _redis_wrapper())
    connect_svc.user_repository = AsyncMock()
    connect_svc.key_repository = AsyncMock()
    connect_svc.placement_repository = AsyncMock()
    connect_svc.node_repository = AsyncMock()
    connect_svc.route_repository = AsyncMock()

    connect_svc.user_repository.get_by_id = AsyncMock(return_value=MagicMock(id=user_id))
    connect_svc.key_repository.get_latest_active_for_user = AsyncMock(return_value=key)
    connect_svc.placement_repository.get_by_key_id = AsyncMock(return_value=placement)
    connect_svc.node_repository.get_by_id = AsyncMock(return_value=backend)
    connect_svc.route_repository.list_resolved_active = AsyncMock(
        return_value=[(route, backend, tp)]
    )
    connect_svc._build_route_uri = MagicMock(return_value="vless://route")

    connect_out = await connect_svc.connect_routeset(
        ConnectRouteSetIn(user_id=user_id, max_routes=1)
    )
    assert connect_out.routes
    route_id = connect_out.routes[0].route_id
    assert route_id == route.id

    route_repository = AsyncMock()

    async def _get_by_id(item_id):
        if item_id == route.id:
            return route
        return None

    async def _update_by_id(item_id, data):
        assert item_id == route.id
        for key_name, value in data.items():
            setattr(route, key_name, _normalize_value(value))
        return route

    async def _list_warming_up():
        if route.is_active and route.health_status == "warming_up":
            return [route]
        return []

    route_repository.get_by_id = AsyncMock(side_effect=_get_by_id)
    route_repository.update_by_id = AsyncMock(side_effect=_update_by_id)
    route_repository.list_warming_up = AsyncMock(side_effect=_list_warming_up)

    route_svc = RouteService(async_session)
    route_svc.route_repository = route_repository

    redis_client = AsyncMock()
    redis_client.sismember = AsyncMock(return_value=1)
    redis_client.set = AsyncMock(return_value=True)
    redis_client.sadd = AsyncMock(return_value=1)
    redis_client.expire = AsyncMock(return_value=True)
    redis_client.scard = AsyncMock(side_effect=[1, 2])

    telemetry_svc = ConnectTelemetryService(
        async_session,
        redis_client=redis_client,
        debounce_sec=1,
        failure_window_sec=300,
        failure_degraded_threshold=1,
        failure_block_threshold=2,
        block_cooldown_hours=1,
    )
    telemetry_svc.route_repository = route_repository
    telemetry_svc.route_service = route_svc
    telemetry_svc.key_repository = AsyncMock()
    telemetry_svc.key_repository.get_by_id = AsyncMock(return_value=key)
    telemetry_svc.placement_repository = AsyncMock()
    telemetry_svc.placement_repository.get_by_key_id = AsyncMock(return_value=placement)

    out_1 = await telemetry_svc.report(
        ConnectTelemetryIn(
            route_id=route_id,
            key_id=key_id,
            event=ConnectTelemetryEvent.connect_failure,
        )
    )
    assert out_1.applied_action == RouteHealthAction.set_degraded.value
    assert route.health_status == "degraded"

    out_2 = await telemetry_svc.report(
        ConnectTelemetryIn(
            route_id=route_id,
            key_id=key_id,
            event=ConnectTelemetryEvent.connect_failure,
        )
    )
    assert out_2.applied_action == RouteHealthAction.block.value
    assert route.health_status == "blocked"
    assert route.effective_weight == 0
    assert route.cooldown_until is not None

    with pytest.raises(HTTPException) as exc:
        await route_svc.update_route_health(
            route.id,
            RouteHealthUpdateIn(action=RouteHealthAction.recover, cooldown_hours=1),
        )
    assert exc.value.status_code == 409

    route.cooldown_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await route_svc.update_route_health(
        route.id,
        RouteHealthUpdateIn(action=RouteHealthAction.recover, cooldown_hours=1),
    )
    assert route.health_status == "warming_up"
    assert route.warmup_stage == 0
    assert route.effective_weight == 10

    route.warmup_started_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    tick_1 = await route_svc.advance_warmup()
    assert tick_1.advanced == 1
    assert route.health_status == "warming_up"
    assert route.warmup_stage == 1
    assert route.effective_weight == 25

    route.warmup_started_at = datetime.now(timezone.utc) - timedelta(minutes=61)
    tick_2 = await route_svc.advance_warmup()
    assert tick_2.finalized == 1
    assert route.health_status == "healthy"
    assert route.warmup_stage is None
    assert route.cooldown_until is None
    assert route.effective_weight == route.base_weight
