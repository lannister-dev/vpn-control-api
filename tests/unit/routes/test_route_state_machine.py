from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services.routes.exceptions import RouteCooldownActiveError
from services.routes.schemas import RouteHealthAction, RouteHealthStatus, RouteWarmupTickResult
from services.routes.state_machine import (
    resolve_bootstrap_recovery,
    resolve_probe_block,
    resolve_probe_recover,
    resolve_route_health_action,
    resolve_warmup_tick,
)


def _route(
        *,
        status: str = "healthy",
        base_weight: int = 50,
        effective_weight: int = 50,
        cooldown_until=None,
        warmup_stage=None,
        warmup_started_at=None,
):
    return SimpleNamespace(
        health_status=status,
        base_weight=base_weight,
        effective_weight=effective_weight,
        cooldown_until=cooldown_until,
        warmup_stage=warmup_stage,
        warmup_started_at=warmup_started_at,
    )


def test_resolve_route_health_action_recover_raises_if_cooldown_active():
    now = datetime.now(timezone.utc)
    route = _route(
        status="blocked",
        effective_weight=0,
        cooldown_until=now + timedelta(minutes=10),
    )

    with pytest.raises(RouteCooldownActiveError):
        resolve_route_health_action(
            route=route,
            action=RouteHealthAction.recover,
            now=now,
            cooldown_hours=6,
        )


def test_resolve_probe_recover_returns_warmup_state_after_cooldown():
    checked_at = datetime.now(timezone.utc)
    route = _route(
        status="blocked",
        base_weight=50,
        effective_weight=0,
        cooldown_until=checked_at - timedelta(seconds=1),
    )

    out = resolve_probe_recover(route=route, checked_at=checked_at)

    assert out is not None
    assert out.health_status == RouteHealthStatus.warming_up
    assert out.effective_weight == 10
    assert out.warmup_stage == 0


def test_resolve_bootstrap_recovery_returns_controlled_warmup_state():
    now = datetime.now(timezone.utc)

    out = resolve_bootstrap_recovery(route_base_weight=25, now=now)

    assert out.health_status == RouteHealthStatus.warming_up
    assert out.effective_weight == 10
    assert out.cooldown_until is None
    assert out.warmup_stage == 0
    assert out.warmup_started_at == now


def test_resolve_warmup_tick_advances_and_finalizes():
    now = datetime.now(timezone.utc)
    route_advance = _route(
        status="warming_up",
        base_weight=50,
        effective_weight=10,
        warmup_stage=0,
        warmup_started_at=now - timedelta(minutes=31),
    )
    next_state, result = resolve_warmup_tick(route=route_advance, now=now)
    assert result == RouteWarmupTickResult.advanced
    assert next_state is not None
    assert next_state.health_status == RouteHealthStatus.warming_up
    assert next_state.effective_weight == 25
    assert next_state.warmup_stage == 1

    route_finalize = _route(
        status="warming_up",
        base_weight=50,
        effective_weight=25,
        warmup_stage=1,
        warmup_started_at=now - timedelta(minutes=61),
    )
    final_state, final_result = resolve_warmup_tick(route=route_finalize, now=now)
    assert final_result == RouteWarmupTickResult.finalized
    assert final_state is not None
    assert final_state.health_status == RouteHealthStatus.healthy
    assert final_state.effective_weight == 50
    assert final_state.warmup_stage is None


def test_resolve_probe_block_sets_zero_weight_and_cooldown():
    checked_at = datetime.now(timezone.utc)
    route = _route()

    out = resolve_probe_block(route=route, checked_at=checked_at, cooldown_hours=6)

    assert out.health_status == RouteHealthStatus.blocked
    assert out.effective_weight == 0
    assert out.cooldown_until == checked_at + timedelta(hours=6)


def test_resolve_route_health_action_block_with_zero_cooldown_clears_cooldown_until():
    now = datetime.now(timezone.utc)
    route = _route()

    out = resolve_route_health_action(
        route=route,
        action=RouteHealthAction.block,
        now=now,
        cooldown_hours=0,
    )

    assert out.health_status == RouteHealthStatus.blocked
    assert out.effective_weight == 0
    assert out.cooldown_until is None


def test_resolve_probe_recover_returns_warmup_when_cooldown_disabled():
    checked_at = datetime.now(timezone.utc)
    route = _route(
        status="blocked",
        base_weight=50,
        effective_weight=0,
        cooldown_until=None,
    )

    out = resolve_probe_recover(route=route, checked_at=checked_at)

    assert out is not None
    assert out.health_status == RouteHealthStatus.warming_up
    assert out.warmup_stage == 0
