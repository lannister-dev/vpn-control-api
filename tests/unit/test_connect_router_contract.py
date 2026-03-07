from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.connect.router import connect_routeset, connect_telemetry
from services.connect.schemas import (
    ConnectRouteOut,
    ConnectRouteSetIn,
    ConnectRouteSetOut,
    ConnectTelemetryEvent,
    ConnectTelemetryIn,
    ConnectTelemetryOut,
    ConnectTelemetryStatus,
)


@pytest.mark.asyncio
async def test_connect_routeset_contract():
    payload = ConnectRouteSetIn(user_id=uuid4(), max_routes=3)
    route = ConnectRouteOut(
        route_id=uuid4(),
        route_name="be1-reality-google",
        backend_node_id=uuid4(),
        transport_profile_id=uuid4(),
        health_status="healthy",
        effective_weight=40,
        uri="vless://route1",
    )
    out_expected = ConnectRouteSetOut(
        key_id=uuid4(),
        client_id=str(uuid4()),
        placement_id=uuid4(),
        placement_op_version=3,
        config_version=3,
        selection_strategy="ordered_fallback",
        refresh_interval_sec=60,
        max_cache_age_sec=300,
        backoff_steps_sec=[2, 5, 10, 30, 60],
        routes=[route],
    )
    service = SimpleNamespace(connect_routeset=AsyncMock(return_value=out_expected))

    out = await connect_routeset(payload=payload, service=service)

    assert out == out_expected
    service.connect_routeset.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_connect_telemetry_contract():
    route_id = uuid4()
    payload = ConnectTelemetryIn(
        route_id=route_id,
        key_id=uuid4(),
        event=ConnectTelemetryEvent.connect_failure,
        error="timeout",
    )
    out_expected = ConnectTelemetryOut(
        status=ConnectTelemetryStatus.accepted,
        route_id=route_id,
        applied_action="set_suspected",
        failure_streak=1,
    )
    service = SimpleNamespace(report=AsyncMock(return_value=out_expected))

    out = await connect_telemetry(payload=payload, service=service)

    assert out == out_expected
    service.report.assert_awaited_once_with(payload)
