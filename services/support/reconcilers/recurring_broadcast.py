from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.support.constants import SUPPORT_OUTBOUND_SUBJECT
from services.support.service import SupportService
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("recurring-broadcast-reconciler"))


class RecurringBroadcastReconciler(Reconciler):
    name = "recurring_broadcast"

    def __init__(
        self,
        *,
        nats_client: NatsClient | None = None,
        interval_sec: int = 60,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(interval_sec=max(30, int(interval_sec)), tick_lock=tick_lock)
        self._nats_client = nats_client
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._session_maker() as session:
            service = SupportService(
                session,
                nats_client=self._nats_client,
                outbound_subject=SUPPORT_OUTBOUND_SUBJECT,
            )
            created = await service.materialize_due_recurring(now)
            if created:
                logger.info("recurring_broadcasts_dispatched", count=created)
            return created
