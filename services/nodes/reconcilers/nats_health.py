from __future__ import annotations

import logging

import httpx

from services.alerts.constants import AlertSource
from services.alerts.schemas import AlertLevel
from services.alerts.service import AlertService
from services.config import get_settings
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("nats-health-reconciler"))

MEM_WARN_BYTES = 700 * 1024 * 1024
SLOW_CONSUMERS_WARN = 50


class NatsHealthReconciler(Reconciler):
    name = "nats_health"

    def __init__(
        self,
        *,
        interval_sec: int = 60,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(interval_sec=max(30, int(interval_sec)), tick_lock=tick_lock, lock_ttl_sec=120)
        self._session_maker = AsyncDatabase.get_session_maker()
        self._prev_uptime_sec: float | None = None

    async def is_enabled(self) -> bool:
        return bool(get_settings().nats.monitoring_url)

    async def tick(self) -> int:
        url = get_settings().nats.monitoring_url
        if not url:
            return 0
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url.rstrip("/") + "/varz")
                varz = resp.json()
        except Exception as exc:
            logger.warning("nats_varz_unreachable", url=url, error=str(exc))
            return 0

        mem = int(varz.get("mem", 0))
        uptime = float(varz.get("uptime_sec", 0)) or _parse_uptime(varz.get("uptime", ""))
        slow = int(varz.get("slow_consumers", 0))
        alerts = 0

        if self._prev_uptime_sec is not None and uptime < self._prev_uptime_sec:
            await self._alert(
                AlertLevel.critical, "NATS перезапустился",
                f"uptime сбросился ({int(uptime)}с) — вероятен краш/OOM. mem={mem // 1048576}MB", "nats-restart",
            )
            alerts += 1
        self._prev_uptime_sec = uptime

        if mem >= MEM_WARN_BYTES:
            await self._alert(
                AlertLevel.warning, "NATS: высокая память",
                f"mem={mem // 1048576}MB (порог {MEM_WARN_BYTES // 1048576}MB) — риск OOM", "nats-mem",
            )
            alerts += 1
        else:
            await self._resolve("nats-mem")

        if slow >= SLOW_CONSUMERS_WARN:
            await self._alert(
                AlertLevel.warning, "NATS: slow consumers",
                f"slow_consumers={slow} (порог {SLOW_CONSUMERS_WARN})", "nats-slow",
            )
            alerts += 1
        else:
            await self._resolve("nats-slow")

        return alerts

    async def _alert(self, level: AlertLevel, title: str, body: str, key: str) -> None:
        try:
            async with self._session_maker() as session:
                await AlertService(session).record(
                    level=level, title=title, body=body,
                    source=AlertSource.NATS, dedup_key=key,
                )
                await session.commit()
        except Exception:
            logger.exception("nats_health_alert_failed", key=key)

    async def _resolve(self, key: str) -> None:
        try:
            async with self._session_maker() as session:
                await AlertService(session).resolve(source=AlertSource.NATS, dedup_key=key)
                await session.commit()
        except Exception:
            logger.exception("nats_health_resolve_failed", key=key)


def _parse_uptime(s: str) -> float:
    total = 0.0
    num = ""
    units = {"y": 31536000, "d": 86400, "h": 3600, "m": 60, "s": 1}
    for ch in s:
        if ch.isdigit():
            num += ch
        elif ch in units and num:
            total += int(num) * units[ch]
            num = ""
    return total
