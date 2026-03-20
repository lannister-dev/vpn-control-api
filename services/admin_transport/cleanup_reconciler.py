from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from services.admin_transport.repository import AdminTransportRepository
from services.config import TransportConfig, get_settings
from shared.database.session import AsyncDatabase
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger


logger = StructuredLogger(logging.getLogger("transport-cleanup-reconciler"))


class AdminTransportCleanupReconciler:
    def __init__(
            self,
            *,
            transport_settings: TransportConfig | None = None,
            tick_lock: RedisTickLock | None = None,
    ):
        settings = transport_settings or get_settings().transport
        self._enabled = bool(settings.cleanup_enabled)
        self._interval_sec = max(300, int(settings.cleanup_tick_sec))
        self._retention_days = max(1, int(settings.retention_days))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:transport_cleanup",
            ttl_sec=max(300, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("transport_cleanup_disabled")
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

    async def run_once(self) -> tuple[int, int] | None:
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
                logger.exception("transport_cleanup_tick_failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self) -> tuple[int, int]:
        async with self._session_maker() as session:
            repo = AdminTransportRepository(session)
            cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
            deleted_outbox = await repo.delete_published_outbox_older_than(cutoff=cutoff)
            deleted_events = await repo.delete_events_older_than(cutoff=cutoff)
            await session.commit()
            if deleted_outbox > 0 or deleted_events > 0:
                logger.info(
                    "transport_cleanup_tick",
                    deleted_outbox=deleted_outbox,
                    deleted_events=deleted_events,
                    retention_days=self._retention_days,
                )
            return deleted_outbox, deleted_events
