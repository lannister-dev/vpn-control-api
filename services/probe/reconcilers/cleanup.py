from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from services.probe.constants import CLEANUP_IDLE_WHEN_DISABLED_SEC
from services.probe.policy.repository import ProbePolicyRepository
from services.probe.repository import ProbeSignalRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("probe-cleanup-reconciler"))


class ProbeSignalCleanupReconciler:
    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:probe_cleanup",
            ttl_sec=7200,
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
        async with self._session_maker() as session:
            policy = (await ProbePolicyRepository(session).list(limit=1))[0]
            await session.commit()
        if not policy.cleanup_enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._execute_tick(policy.retention_days)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            sleep_sec = CLEANUP_IDLE_WHEN_DISABLED_SEC
            try:
                async with self._session_maker() as session:
                    policy = (await ProbePolicyRepository(session).list(limit=1))[0]
                    await session.commit()
                sleep_sec = max(300, int(policy.cleanup_tick_sec))
                if policy.cleanup_enabled:
                    async with self._tick_lock.hold() as acquired:
                        if acquired:
                            await self._execute_tick(policy.retention_days)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("probe_cleanup_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self, retention_days: int) -> int:
        retention = max(1, int(retention_days))
        async with self._session_maker() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
            deleted = await ProbeSignalRepository(session).delete_older_than(cutoff=cutoff)
            await session.commit()
            if deleted > 0:
                logger.info(
                    "probe_cleanup_tick",
                    deleted=deleted,
                    retention_days=retention,
                )
            return deleted
