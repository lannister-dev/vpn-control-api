from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from services.admin_transport.policy.repository import TransportPolicyRepository
from services.admin_transport.repository import AdminTransportRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger


logger = StructuredLogger(logging.getLogger("transport-cleanup-reconciler"))


class AdminTransportCleanupReconciler:
    """Background cleanup of transport event_log / published outbox rows.

    Reads cleanup_enabled / cleanup_tick_sec / retention_days from
    `transport_policy` table on every tick — admin UI edits picked up live.
    """

    _IDLE_WHEN_DISABLED_SEC = 300

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

    async def run_once(self) -> tuple[int, int] | None:
        async with self._session_maker() as session:
            policy = await TransportPolicyRepository(session).get_current()
            await session.commit()
        if not policy.cleanup_enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._execute_tick(policy.retention_days)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            sleep_sec = self._IDLE_WHEN_DISABLED_SEC
            try:
                async with self._session_maker() as session:
                    policy = await TransportPolicyRepository(session).get_current()
                    await session.commit()
                sleep_sec = max(300, int(policy.cleanup_tick_sec))
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

    async def _execute_tick(self, retention_days: int) -> tuple[int, int]:
        retention = max(1, int(retention_days))
        async with self._session_maker() as session:
            repo = AdminTransportRepository(session)
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
            deleted_outbox = await repo.delete_published_outbox_older_than(cutoff=cutoff)
            deleted_events = await repo.delete_events_older_than(cutoff=cutoff)
            await session.commit()
            if deleted_outbox > 0 or deleted_events > 0:
                logger.info(
                    "transport_cleanup_tick",
                    deleted_outbox=deleted_outbox,
                    deleted_events=deleted_events,
                    retention_days=retention,
                )
            return deleted_outbox, deleted_events
