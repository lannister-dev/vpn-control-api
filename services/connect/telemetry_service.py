from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as redis
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.connect.cache_keys import connect_telemetry_allowed_routes_key
from services.connect.schemas import (
    ConnectTelemetryEvent,
    ConnectTelemetryIn,
    ConnectTelemetryOut,
    ConnectTelemetryStatus,
)
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.vpn.keys.repository import VpnKeyRepository
from services.routes.schemas import RouteHealthAction, RouteHealthStatus, RouteHealthUpdateIn
from services.routes.service import RouteService
from services.routes.repository import RouteRepository
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import CONNECT_TELEMETRY_TOTAL
from shared.redis.client import RedisClient, get_redis_client
from shared.utils.logger import StructuredLogger


logger_connect_telemetry = StructuredLogger(logging.getLogger("connect-telemetry-service"))


class ConnectTelemetryService:
    def __init__(
            self,
            session: AsyncSession,
            *,
            redis_client: redis.Redis,
            debounce_sec: int,
            failure_window_sec: int,
            failure_degraded_threshold: int,
            failure_block_threshold: int,
            block_cooldown_hours: int,
    ):
        self.route_repository = RouteRepository(session)
        self.key_repository = VpnKeyRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.route_service = RouteService(session)
        self.redis = redis_client

        self.debounce_sec = max(1, debounce_sec)
        self.failure_window_sec = max(30, failure_window_sec)
        self.failure_block_threshold = max(2, failure_block_threshold)
        self.failure_degraded_threshold = max(1, failure_degraded_threshold)
        if self.failure_degraded_threshold >= self.failure_block_threshold:
            self.failure_degraded_threshold = self.failure_block_threshold - 1
        self.block_cooldown_hours = max(1, block_cooldown_hours)

    async def report(self, payload: ConnectTelemetryIn) -> ConnectTelemetryOut:
        await self._validate_key(payload.key_id)
        route = await self.route_repository.get_by_id(payload.route_id)
        if route is None or not route.is_active:
            raise HTTPException(status_code=404, detail="Route not found")
        await self._validate_key_placement(payload.key_id)
        await self._validate_route_allowed_for_key(
            key_id=payload.key_id,
            route_id=payload.route_id,
        )

        accepted = await self._acquire_debounce(
            route_id=payload.route_id,
            key_id=payload.key_id,
            event=payload.event.value,
        )
        if not accepted:
            out = ConnectTelemetryOut(
                status=ConnectTelemetryStatus.skipped,
                route_id=payload.route_id,
            )
            self._observe(payload=payload, out=out)
            return out

        if payload.event == ConnectTelemetryEvent.connect_success:
            remaining_failures = await self._clear_failure_signal(
                route_id=payload.route_id,
                key_id=payload.key_id,
            )
            if route.health_status in {RouteHealthStatus.suspected.value, RouteHealthStatus.degraded.value}:
                if remaining_failures <= 0:
                    out = await self._apply_action(
                        route_id=payload.route_id,
                        action=RouteHealthAction.set_healthy,
                    )
                else:
                    out = ConnectTelemetryOut(
                        status=ConnectTelemetryStatus.accepted,
                        route_id=payload.route_id,
                        failure_streak=remaining_failures,
                    )
                self._observe(payload=payload, out=out)
                return out
            out = ConnectTelemetryOut(
                status=ConnectTelemetryStatus.accepted,
                route_id=payload.route_id,
            )
            self._observe(payload=payload, out=out)
            return out

        if route.health_status in {RouteHealthStatus.blocked.value, RouteHealthStatus.warming_up.value}:
            out = ConnectTelemetryOut(
                status=ConnectTelemetryStatus.accepted,
                route_id=payload.route_id,
            )
            self._observe(payload=payload, out=out)
            return out

        failure_signals = await self._record_failure_signal(
            route_id=payload.route_id,
            key_id=payload.key_id,
        )
        if failure_signals >= self.failure_block_threshold:
            out = await self._apply_action(
                route_id=payload.route_id,
                action=RouteHealthAction.block,
                failure_streak=failure_signals,
            )
            self._observe(payload=payload, out=out)
            return out

        if failure_signals >= self.failure_degraded_threshold:
            if route.health_status == RouteHealthStatus.degraded.value:
                out = ConnectTelemetryOut(
                    status=ConnectTelemetryStatus.accepted,
                    route_id=payload.route_id,
                    failure_streak=failure_signals,
                )
            else:
                out = await self._apply_action(
                    route_id=payload.route_id,
                    action=RouteHealthAction.set_degraded,
                    failure_streak=failure_signals,
                )
            self._observe(payload=payload, out=out)
            return out

        if route.health_status == RouteHealthStatus.suspected.value:
            out = ConnectTelemetryOut(
                status=ConnectTelemetryStatus.accepted,
                route_id=payload.route_id,
                failure_streak=failure_signals,
            )
        else:
            out = await self._apply_action(
                route_id=payload.route_id,
                action=RouteHealthAction.set_suspected,
                failure_streak=failure_signals,
            )
        self._observe(payload=payload, out=out)
        return out

    async def _acquire_debounce(self, *, route_id: UUID, key_id: UUID, event: str) -> bool:
        key = self._debounce_key(route_id=route_id, key_id=key_id, event=event)
        try:
            locked = await self.redis.set(key, "1", ex=self.debounce_sec, nx=True)
            return bool(locked)
        except Exception:
            logger_connect_telemetry.exception(
                "connect_telemetry_debounce_failed",
                route_id=str(route_id),
                event=event,
            )
            return True

    async def _record_failure_signal(self, *, route_id: UUID, key_id: UUID) -> int:
        key = self._failure_signal_key(route_id=route_id)
        try:
            await self.redis.sadd(key, str(key_id))
            await self.redis.expire(key, self.failure_window_sec)
            return int(await self.redis.scard(key))
        except Exception:
            logger_connect_telemetry.exception(
                "connect_telemetry_failure_signal_record_failed",
                route_id=str(route_id),
            )
            return 1

    async def _clear_failure_signal(self, *, route_id: UUID, key_id: UUID) -> int:
        key = self._failure_signal_key(route_id=route_id)
        try:
            await self.redis.srem(key, str(key_id))
            return int(await self.redis.scard(key))
        except Exception:
            logger_connect_telemetry.exception(
                "connect_telemetry_failure_signal_clear_failed",
                route_id=str(route_id),
            )
            return 0

    @staticmethod
    def _debounce_key(*, route_id: UUID, key_id: UUID, event: str) -> str:
        return f"connect:telemetry:debounce:{route_id}:{key_id}:{event}"

    @staticmethod
    def _failure_signal_key(*, route_id: UUID) -> str:
        return f"connect:telemetry:failure_signals:{route_id}"

    async def _validate_key(self, key_id: UUID) -> None:
        key = await self.key_repository.get_by_id(key_id)
        if key is None or not key.is_active:
            raise HTTPException(status_code=404, detail="Key not found")
        if key.is_revoked:
            raise HTTPException(status_code=409, detail="Key is revoked")
        valid_until = key.valid_until
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        if valid_until <= datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="Key is expired")

    async def _validate_key_placement(self, key_id: UUID) -> None:
        placement = await self.placement_repository.get_by_key_id(key_id)
        if placement is None:
            raise HTTPException(status_code=409, detail="Placement not found for key")
        if placement.desired_state != PlacementDesiredState.active.value:
            raise HTTPException(status_code=409, detail="Placement is not active")

    async def _validate_route_allowed_for_key(self, *, key_id: UUID, route_id: UUID) -> None:
        cache_key = connect_telemetry_allowed_routes_key(key_id=key_id)
        try:
            allowed = bool(await self.redis.sismember(cache_key, str(route_id)))
        except Exception:
            logger_connect_telemetry.exception(
                "connect_telemetry_allowed_routes_check_failed",
                key_id=str(key_id),
                route_id=str(route_id),
            )
            return
        if not allowed:
            raise HTTPException(status_code=409, detail="Route is not allowed for key")

    async def _apply_action(
            self,
            *,
            route_id: UUID,
            action: RouteHealthAction,
            failure_streak: int | None = None,
    ) -> ConnectTelemetryOut:
        await self.route_service.update_route_health(
            route_id,
            RouteHealthUpdateIn(
                action=action,
                cooldown_hours=self.block_cooldown_hours,
            ),
        )
        return ConnectTelemetryOut(
            status=ConnectTelemetryStatus.accepted,
            route_id=route_id,
            applied_action=action.value,
            failure_streak=failure_streak,
        )

    @staticmethod
    def _observe(*, payload: ConnectTelemetryIn, out: ConnectTelemetryOut) -> None:
        action = out.applied_action or "none"
        CONNECT_TELEMETRY_TOTAL.labels(
            event=payload.event.value,
            status=out.status.value,
            action=action,
        ).inc()


def get_connect_telemetry_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
        redis_client: RedisClient = Depends(get_redis_client),
) -> ConnectTelemetryService:
    routes_cfg = get_settings().routes
    return ConnectTelemetryService(
        session,
        redis_client=redis_client.client,
        debounce_sec=routes_cfg.connect_telemetry_debounce_sec,
        failure_window_sec=routes_cfg.connect_telemetry_failure_window_sec,
        failure_degraded_threshold=routes_cfg.connect_telemetry_degraded_threshold,
        failure_block_threshold=routes_cfg.connect_telemetry_block_threshold,
        block_cooldown_hours=routes_cfg.connect_telemetry_block_cooldown_hours,
    )
