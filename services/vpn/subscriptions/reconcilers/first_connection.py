from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.vpn.subscriptions.repository import SubscriptionRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("first-connection-reconciler"))


class FirstConnectionReconciler(Reconciler):
    name = "first_connection"

    def __init__(
        self,
        *,
        interval_sec: int = 120,
        batch_size: int = 500,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(interval_sec=max(30, int(interval_sec)), tick_lock=tick_lock)
        self._batch_size = max(1, int(batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
        async with self._session_maker() as session:
            repo = SubscriptionRepository(session)
            now = datetime.now(timezone.utc)
            stamped = await repo.stamp_first_connection(now=now, limit=self._batch_size)
            if not stamped:
                return 0
            await session.commit()
            logger.info("first_connection_stamped", count=len(stamped))
            return len(stamped)
