from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from services.admin_transport.constants import (
    CLEANUP_IDLE_WHEN_DISABLED_SEC,
    NATS_DEDUP_RETENTION_HOURS,
)
from services.admin_transport.policy.repository import TransportPolicyRepository
from services.admin_transport.repository import AdminTransportRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("transport-cleanup-reconciler"))


class AdminTransportCleanupReconciler:
    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:transport_cleanup",
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

    async def run_once(self) -> tuple[int, int, int] | None:
        async with self._session_maker() as session:
            policy = (await TransportPolicyRepository(session).list(limit=1))[0]
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
                    policy = (await TransportPolicyRepository(session).list(limit=1))[0]
                    await session.commit()
                sleep_sec = max(CLEANUP_IDLE_WHEN_DISABLED_SEC, int(policy.cleanup_tick_sec))
                if policy.cleanup_enabled:
                    async with self._tick_lock.hold() as acquired:
                        if acquired:
                            await self._execute_tick(policy.retention_days)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("transport_cleanup_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self, retention_days: int) -> tuple[int, int, int]:
        retention = max(1, int(retention_days))
        async with self._session_maker() as session:
            repo = AdminTransportRepository(session)
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=retention)
            dedup_cutoff = now - timedelta(hours=NATS_DEDUP_RETENTION_HOURS)
            deleted_outbox = await repo.delete_published_outbox_older_than(cutoff=cutoff)
            deleted_events = await repo.delete_events_older_than(cutoff=cutoff)
            deleted_dedup = await repo.delete_nats_dedup_older_than(cutoff=dedup_cutoff)
            await session.commit()
            if deleted_outbox > 0 or deleted_events > 0 or deleted_dedup > 0:
                logger.info(
                    "transport_cleanup_tick",
                    deleted_outbox=deleted_outbox,
                    deleted_events=deleted_events,
                    deleted_dedup=deleted_dedup,
                    retention_days=retention,
                )
            return deleted_outbox, deleted_events, deleted_dedup
