from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from services.config import NatsDedupConfig, get_settings
from services.nats_dedup.repository import NatsMessageDedupRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("nats-dedup-cleanup-reconciler"))


class NatsDedupCleanupReconciler:
    def __init__(
        self,
        *,
        settings: NatsDedupConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        cfg = settings or get_settings().nats_dedup
        self._enabled = bool(cfg.cleanup_enabled)
        self._interval_sec = max(60, int(cfg.cleanup_tick_sec))
        self._retention = timedelta(seconds=max(60, int(cfg.retention_sec)))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:nats_dedup_cleanup",
            ttl_sec=max(120, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("nats_dedup_cleanup_disabled")
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
                logger.exception("nats_dedup_cleanup_tick_failed")

            watchdog.heartbeat(
                self.__class__.__name__,
                max_silence_sec=self._interval_sec * 2 + 60,
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        async with self._session_maker() as session:
            repo = NatsMessageDedupRepository(session)
            deleted = await repo.cleanup_older_than(retention=self._retention)
            if deleted:
                await session.commit()
                logger.info("nats_dedup_cleanup_done", deleted=deleted)
            return deleted
