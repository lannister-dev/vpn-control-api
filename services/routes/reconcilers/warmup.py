from __future__ import annotations

import asyncio
import logging

from services.config import get_settings
from services.routes.service import RouteService
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger


class RouteWarmupReconciler:
    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._interval_sec = max(30, get_settings().routes.warmup_tick_sec)
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:route_warmup",
            ttl_sec=max(30, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._log = StructuredLogger(logging.getLogger("route-warmup-reconciler"))

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

    async def run_once(self):
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
                self._log.exception("route_warmup_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self):
        async with self._session_maker() as session:
            tick = await RouteService(session).advance_warmup()
            await session.commit()
            if tick.processed > 0:
                self._log.info(
                    "route_warmup_tick",
                    processed=tick.processed,
                    advanced=tick.advanced,
                    finalized=tick.finalized,
                )
            return tick
