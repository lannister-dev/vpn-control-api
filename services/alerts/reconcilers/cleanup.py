from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from services.alerts.repository import AlertEventRepository
from services.config import AlertsConfig, get_settings
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("alerts-cleanup-reconciler"))


class AlertsCleanupReconciler:
    def __init__(
        self,
        *,
        config: AlertsConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        settings = get_settings()
        self._cfg = config or settings.alerts
        self._interval_sec = max(300, int(self._cfg.cleanup_tick_sec))
        self._retention_days = max(1, int(self._cfg.cleanup_retention_days))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:alerts_cleanup",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
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
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._tick()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("alerts_cleanup_tick_failed")
            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        async with self._session_maker() as session:
            deleted = await AlertEventRepository(session).delete_older_than(cutoff=cutoff)
            await session.commit()
        if deleted:
            logger.info("alerts_cleanup_applied", deleted=deleted, retention_days=self._retention_days)
        return deleted
