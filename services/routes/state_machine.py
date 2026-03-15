from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from services.routes.schemas import RouteHealthAction, RouteHealthStatus

WarmupTickResult = Literal["advanced", "finalized"]

DEFAULT_WARMUP_STAGES: tuple[tuple[int, int], ...] = (
    (10, 30),
    (25, 60),
)


class RouteCooldownActiveError(ValueError):
    pass


def initial_warmup_weight(*, base_weight: int) -> int:
    if base_weight <= 0:
        return 0
    return min(int(base_weight), int(DEFAULT_WARMUP_STAGES[0][0]))


def stage_weight(
        *,
        base_weight: int,
        stage: int,
        warmup_stages: tuple[tuple[int, int], ...] = DEFAULT_WARMUP_STAGES,
) -> int:
    if base_weight <= 0:
        return 0
    if stage >= len(warmup_stages):
        return int(base_weight)
    stage_target_weight, _hold_minutes = warmup_stages[stage]
    return min(int(base_weight), int(stage_target_weight))


def resolve_route_health_action(
        *,
        route,
        action: RouteHealthAction,
        now: datetime,
        cooldown_hours: int,
        warmup_stages: tuple[tuple[int, int], ...] = DEFAULT_WARMUP_STAGES,
) -> dict:
    status = str(route.health_status)
    effective_weight = int(route.effective_weight)
    cooldown_until = _to_utc_or_none(route.cooldown_until)
    warmup_stage = route.warmup_stage
    warmup_started_at = _to_utc_or_none(route.warmup_started_at)

    if action == RouteHealthAction.block:
        status = RouteHealthStatus.blocked.value
        effective_weight = 0
        cooldown_until = now + timedelta(hours=cooldown_hours)
        warmup_stage = None
        warmup_started_at = None
    elif action == RouteHealthAction.recover:
        if cooldown_until is not None and cooldown_until > now:
            raise RouteCooldownActiveError("Route is still in cooldown")
        status = RouteHealthStatus.warming_up.value
        warmup_stage = 0
        warmup_started_at = now
        effective_weight = stage_weight(
            base_weight=int(route.base_weight),
            stage=0,
            warmup_stages=warmup_stages,
        )
        cooldown_until = None
    elif action == RouteHealthAction.set_healthy:
        status = RouteHealthStatus.healthy.value
        effective_weight = int(route.base_weight)
        cooldown_until = None
        warmup_stage = None
        warmup_started_at = None
    elif action == RouteHealthAction.set_degraded:
        status = RouteHealthStatus.degraded.value
        effective_weight = max(1, min(int(route.base_weight), int(route.base_weight) // 2))
        cooldown_until = None
        warmup_stage = None
        warmup_started_at = None
    elif action == RouteHealthAction.set_suspected:
        status = RouteHealthStatus.suspected.value
        effective_weight = max(1, min(int(route.base_weight), int(route.base_weight) // 3))
        cooldown_until = None
        warmup_stage = None
        warmup_started_at = None

    return {
        "health_status": RouteHealthStatus(status),
        "effective_weight": effective_weight,
        "cooldown_until": cooldown_until,
        "warmup_stage": warmup_stage,
        "warmup_started_at": warmup_started_at,
    }


def resolve_probe_block(
        *,
        route,
        checked_at: datetime,
        cooldown_hours: int,
) -> dict:
    return {
        "health_status": RouteHealthStatus.blocked,
        "effective_weight": 0,
        "cooldown_until": checked_at + timedelta(hours=cooldown_hours),
        "warmup_stage": None,
        "warmup_started_at": None,
    }


def resolve_probe_recover(*, route, checked_at: datetime) -> dict | None:
    if str(route.health_status) != RouteHealthStatus.blocked.value:
        return None
    cooldown_until = _to_utc_or_none(route.cooldown_until)
    if cooldown_until is not None and cooldown_until > checked_at:
        return None
    return {
        "health_status": RouteHealthStatus.warming_up,
        "effective_weight": initial_warmup_weight(base_weight=int(route.base_weight)),
        "cooldown_until": None,
        "warmup_stage": 0,
        "warmup_started_at": checked_at,
    }


def resolve_bootstrap_recovery(
        *,
        route_base_weight: int,
        now: datetime,
) -> dict:
    return {
        "health_status": RouteHealthStatus.warming_up,
        "effective_weight": initial_warmup_weight(base_weight=int(route_base_weight)),
        "cooldown_until": None,
        "warmup_stage": 0,
        "warmup_started_at": now,
    }


def resolve_warmup_tick(
        *,
        route,
        now: datetime,
        warmup_stages: tuple[tuple[int, int], ...] = DEFAULT_WARMUP_STAGES,
) -> tuple[dict | None, WarmupTickResult | None]:
    stage = route.warmup_stage
    started = _to_utc_or_none(route.warmup_started_at)
    if stage is None or started is None:
        return _healthy_state(route=route), "finalized"

    if stage >= len(warmup_stages):
        return _healthy_state(route=route), "finalized"

    _weight, hold_minutes = warmup_stages[stage]
    elapsed_minutes = (now - started).total_seconds() / 60
    if elapsed_minutes < hold_minutes:
        return None, None

    next_stage = stage + 1
    if next_stage >= len(warmup_stages):
        return _healthy_state(route=route), "finalized"

    return {
        "health_status": RouteHealthStatus.warming_up,
        "effective_weight": stage_weight(
            base_weight=int(route.base_weight),
            stage=next_stage,
            warmup_stages=warmup_stages,
        ),
        "cooldown_until": None,
        "warmup_stage": next_stage,
        "warmup_started_at": now,
    }, "advanced"


def _healthy_state(*, route) -> dict:
    return {
        "health_status": RouteHealthStatus.healthy,
        "effective_weight": int(route.base_weight),
        "cooldown_until": None,
        "warmup_stage": None,
        "warmup_started_at": None,
    }


def _to_utc_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
