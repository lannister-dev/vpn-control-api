from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.connect.schemas import ConnectTelemetryEvent, ConnectTelemetryIn
from services.connect.telemetry_service import ConnectTelemetryService
from services.routes.schemas import RouteHealthAction


def _route(*, status: str = "healthy", is_active: bool = True):
    route = MagicMock()
    route.id = uuid4()
    route.health_status = status
    route.is_active = is_active
    return route


def _service(async_session) -> ConnectTelemetryService:
    redis = AsyncMock()
    svc = ConnectTelemetryService(
        async_session,
        redis_client=redis,
        debounce_sec=10,
        failure_window_sec=300,
        failure_degraded_threshold=2,
        failure_block_threshold=3,
        block_cooldown_hours=1,
    )
    key = MagicMock()
    key.is_active = True
    key.is_revoked = False
    key.valid_until = datetime.now(timezone.utc) + timedelta(hours=1)
    svc.key_repository = AsyncMock()
    svc.key_repository.get_by_id.return_value = key
    placement = MagicMock()
    placement.desired_state = "active"
    svc.placement_repository = AsyncMock()
    svc.placement_repository.list_by_key_id.return_value = [placement]
    svc.redis.sismember = AsyncMock(return_value=1)
    return svc


@pytest.mark.asyncio
async def test_telemetry_rejects_unknown_route(async_session):
    svc = _service(async_session)
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await svc.report(
            ConnectTelemetryIn(
                route_id=uuid4(),
                key_id=uuid4(),
                event=ConnectTelemetryEvent.connect_failure,
            )
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_telemetry_rejects_revoked_key(async_session):
    svc = _service(async_session)
    key = MagicMock()
    key.is_active = True
    key.is_revoked = True
    key.valid_until = datetime.now(timezone.utc) + timedelta(hours=1)
    svc.key_repository.get_by_id.return_value = key

    with pytest.raises(HTTPException) as exc:
        await svc.report(
            ConnectTelemetryIn(
                route_id=uuid4(),
                key_id=uuid4(),
                event=ConnectTelemetryEvent.connect_failure,
            )
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "Key is revoked"


@pytest.mark.asyncio
async def test_telemetry_rejects_route_not_allowed_for_key(async_session):
    svc = _service(async_session)
    route = _route(status="healthy")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.redis.sismember = AsyncMock(return_value=0)

    with pytest.raises(HTTPException) as exc:
        await svc.report(
            ConnectTelemetryIn(
                route_id=route.id,
                key_id=uuid4(),
                event=ConnectTelemetryEvent.connect_failure,
            )
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "Route is not allowed for key"


@pytest.mark.asyncio
async def test_telemetry_skips_on_debounce(async_session):
    svc = _service(async_session)
    route = _route(status="healthy")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.route_service = AsyncMock()
    svc.redis.set = AsyncMock(return_value=None)

    out = await svc.report(
        ConnectTelemetryIn(
            route_id=route.id,
            key_id=uuid4(),
            event=ConnectTelemetryEvent.connect_failure,
        )
    )

    assert out.status.value == "skipped"
    assert out.route_id == route.id
    svc.route_service.update_route_health.assert_not_awaited()


@pytest.mark.asyncio
async def test_telemetry_marks_suspected_on_first_failure(async_session):
    svc = _service(async_session)
    route = _route(status="healthy")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.route_service = AsyncMock()
    svc.redis.set = AsyncMock(return_value=True)
    svc.redis.sadd = AsyncMock(return_value=1)
    svc.redis.scard = AsyncMock(return_value=1)
    svc.redis.expire = AsyncMock(return_value=True)

    out = await svc.report(
        ConnectTelemetryIn(
            route_id=route.id,
            key_id=uuid4(),
            event=ConnectTelemetryEvent.connect_failure,
            error="timeout",
        )
    )

    assert out.status.value == "accepted"
    assert out.applied_action == RouteHealthAction.set_suspected.value
    assert out.failure_streak == 1
    svc.route_service.update_route_health.assert_awaited_once()
    action = svc.route_service.update_route_health.await_args.args[1].action
    assert action == RouteHealthAction.set_suspected
    svc.redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_telemetry_blocks_on_failure_threshold(async_session):
    svc = _service(async_session)
    route = _route(status="suspected")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.route_service = AsyncMock()
    svc.redis.set = AsyncMock(return_value=True)
    svc.redis.sadd = AsyncMock(return_value=1)
    svc.redis.scard = AsyncMock(return_value=3)
    svc.redis.expire = AsyncMock(return_value=True)

    out = await svc.report(
        ConnectTelemetryIn(
            route_id=route.id,
            key_id=uuid4(),
            event=ConnectTelemetryEvent.connect_failure,
        )
    )

    assert out.status.value == "accepted"
    assert out.applied_action == RouteHealthAction.block.value
    assert out.failure_streak == 3
    action = svc.route_service.update_route_health.await_args.args[1].action
    assert action == RouteHealthAction.block
    svc.redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_telemetry_degrades_before_block_threshold(async_session):
    svc = _service(async_session)
    route = _route(status="suspected")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.route_service = AsyncMock()
    svc.redis.set = AsyncMock(return_value=True)
    svc.redis.sadd = AsyncMock(return_value=1)
    svc.redis.scard = AsyncMock(return_value=2)
    svc.redis.expire = AsyncMock(return_value=True)

    out = await svc.report(
        ConnectTelemetryIn(
            route_id=route.id,
            key_id=uuid4(),
            event=ConnectTelemetryEvent.connect_failure,
        )
    )

    assert out.status.value == "accepted"
    assert out.applied_action == RouteHealthAction.set_degraded.value
    assert out.failure_streak == 2
    action = svc.route_service.update_route_health.await_args.args[1].action
    assert action == RouteHealthAction.set_degraded
    svc.redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_telemetry_recovers_to_healthy_on_success(async_session):
    svc = _service(async_session)
    route = _route(status="suspected")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.route_service = AsyncMock()
    svc.redis.set = AsyncMock(return_value=True)
    svc.redis.srem = AsyncMock(return_value=1)
    svc.redis.scard = AsyncMock(return_value=0)

    out = await svc.report(
        ConnectTelemetryIn(
            route_id=route.id,
            key_id=uuid4(),
            event=ConnectTelemetryEvent.connect_success,
        )
    )

    assert out.status.value == "accepted"
    assert out.applied_action == RouteHealthAction.set_healthy.value
    action = svc.route_service.update_route_health.await_args.args[1].action
    assert action == RouteHealthAction.set_healthy
    svc.redis.srem.assert_awaited_once()
    svc.redis.scard.assert_awaited_once()


@pytest.mark.asyncio
async def test_telemetry_failure_does_not_override_blocked(async_session):
    svc = _service(async_session)
    route = _route(status="blocked")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.route_service = AsyncMock()
    svc.redis.set = AsyncMock(return_value=True)

    out = await svc.report(
        ConnectTelemetryIn(
            route_id=route.id,
            key_id=uuid4(),
            event=ConnectTelemetryEvent.connect_failure,
        )
    )

    assert out.status.value == "accepted"
    assert out.applied_action is None
    svc.route_service.update_route_health.assert_not_awaited()


@pytest.mark.asyncio
async def test_telemetry_failure_suspected_is_idempotent(async_session):
    svc = _service(async_session)
    route = _route(status="suspected")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.route_service = AsyncMock()
    svc.redis.set = AsyncMock(return_value=True)
    svc.redis.sadd = AsyncMock(return_value=1)
    svc.redis.scard = AsyncMock(return_value=1)
    svc.redis.expire = AsyncMock(return_value=True)

    out = await svc.report(
        ConnectTelemetryIn(
            route_id=route.id,
            key_id=uuid4(),
            event=ConnectTelemetryEvent.connect_failure,
        )
    )

    assert out.status.value == "accepted"
    assert out.applied_action is None
    assert out.failure_streak == 1
    svc.route_service.update_route_health.assert_not_awaited()
    svc.redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_telemetry_failure_degraded_is_idempotent(async_session):
    svc = _service(async_session)
    route = _route(status="degraded")
    svc.route_repository = AsyncMock()
    svc.route_repository.get_by_id.return_value = route
    svc.route_service = AsyncMock()
    svc.redis.set = AsyncMock(return_value=True)
    svc.redis.sadd = AsyncMock(return_value=1)
    svc.redis.scard = AsyncMock(return_value=2)
    svc.redis.expire = AsyncMock(return_value=True)

    out = await svc.report(
        ConnectTelemetryIn(
            route_id=route.id,
            key_id=uuid4(),
            event=ConnectTelemetryEvent.connect_failure,
        )
    )

    assert out.status.value == "accepted"
    assert out.applied_action is None
    assert out.failure_streak == 2
    svc.route_service.update_route_health.assert_not_awaited()
    svc.redis.expire.assert_awaited_once()
