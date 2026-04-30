from __future__ import annotations

import asyncio
import logging

from services.config import TrafficConfig, get_settings
from services.traffic.users.service import UserTrafficService
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("traffic-cleanup-reconciler"))


class TrafficHistoryCleanupReconciler:
    def __init__(
            self,
            *,
            traffic_settings: TrafficConfig | None = None,
            tick_lock: RedisTickLock | None = None,
    ):
        settings = traffic_settings or get_settings().traffic
        self._enabled = bool(settings.cleanup_enabled)
        self._interval_sec = max(300, int(settings.cleanup_tick_sec))
        self._retention_days = max(1, int(settings.history_retention_days))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:traffic_cleanup",
            ttl_sec=max(300, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("traffic_cleanup_disabled")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def run_once(self) -> int | None:
        if not self._enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._execute_tick()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("traffic_cleanup_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        async with self._session_maker() as session:
            deleted = await UserTrafficService(session).cleanup_history(
                retention_days=self._retention_days,
            )
            await session.commit()
            if deleted > 0:
                logger.info(
                    "traffic_cleanup_tick",
                    deleted=deleted,
                    retention_days=self._retention_days,
                )
            return deleted
