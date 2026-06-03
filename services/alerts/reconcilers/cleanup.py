from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from services.alerts.repository import AlertEventRepository
from services.config import AlertsConfig, get_settings
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("alerts-cleanup-reconciler"))


class AlertsCleanupReconciler(Reconciler):
    name = "alerts_cleanup"

    def __init__(
        self,
        *,
        config: AlertsConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        cfg = config or get_settings().alerts
        super().__init__(interval_sec=max(300, int(cfg.cleanup_tick_sec)), tick_lock=tick_lock)
        self._retention_days = max(1, int(cfg.cleanup_retention_days))
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        async with self._session_maker() as session:
            deleted = await AlertEventRepository(session).delete_older_than(cutoff=cutoff)
            await session.commit()
        if deleted:
            logger.info("alerts_cleanup_applied", deleted=deleted, retention_days=self._retention_days)
        return deleted
