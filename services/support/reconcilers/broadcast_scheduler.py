from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from services.support.constants import SUPPORT_OUTBOUND_SUBJECT
from services.support.repository import BroadcastRepository
from services.support.service import SupportService
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("broadcast-scheduler-reconciler"))


class BroadcastSchedulerReconciler:
    def __init__(
        self,
        *,
        nats_client: NatsClient | None = None,
        interval_sec: int = 30,
        batch_size: int = 25,
    ):
        self._nats_client = nats_client
        self._interval_sec = max(15, int(interval_sec))
        self._batch_size = max(1, int(batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = RedisTickLock(
            key="reconciler:broadcast_scheduler",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def run_once(self) -> int | None:
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._execute_tick()

    async def _run(self):
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("broadcast_scheduler_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._session_maker() as session:
            repo = BroadcastRepository(session)
            due = await repo.pick_due_scheduled(now=now, limit=self._batch_size)
            if not due:
                return 0
            service = SupportService(
                session,
                nats_client=self._nats_client,
                outbound_subject=SUPPORT_OUTBOUND_SUBJECT,
            )
            dispatched = 0
            for candidate in due:
                if await service.send_scheduled_broadcast(candidate.id):
                    dispatched += 1
            if dispatched:
                logger.info("broadcasts_dispatched", count=dispatched)
            return dispatched
