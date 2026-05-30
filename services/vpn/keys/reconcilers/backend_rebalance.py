from __future__ import annotations

import asyncio
import logging

from services.config import EntryRoutingConfig, get_settings
from services.vpn.keys.backend_rebalance_service import BackendRebalanceService
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("backend-rebalance-reconciler"))


class BackendRebalanceReconciler:
    def __init__(
        self,
        *,
        routing_config: EntryRoutingConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        settings = get_settings()
        self._cfg = routing_config or settings.entry_routing
        self._enabled = bool(self._cfg.backend_rebalance_enabled)
        self._interval_sec = max(60, int(self._cfg.backend_rebalance_tick_sec))
        self._service = BackendRebalanceService(routing_config=self._cfg)
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:backend_rebalance",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        if not self._enabled:
            logger.info("backend_rebalance_disabled")
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
            return await self._service.run_once()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._enabled:
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("backend_rebalance_tick_failed")
            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue
