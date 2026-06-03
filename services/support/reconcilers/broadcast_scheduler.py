from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.support.constants import SUPPORT_OUTBOUND_SUBJECT
from services.support.repository import BroadcastRepository
from services.support.service import SupportService
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("broadcast-scheduler-reconciler"))


class BroadcastSchedulerReconciler(Reconciler):
    name = "broadcast_scheduler"

    def __init__(
        self,
        *,
        nats_client: NatsClient | None = None,
        interval_sec: int = 30,
        batch_size: int = 25,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(interval_sec=max(15, int(interval_sec)), tick_lock=tick_lock)
        self._nats_client = nats_client
        self._batch_size = max(1, int(batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
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
