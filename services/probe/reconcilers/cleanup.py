from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from services.probe.constants import CLEANUP_IDLE_WHEN_DISABLED_SEC
from services.probe.policy.repository import ProbePolicyRepository
from services.probe.repository import ProbeSignalRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("probe-cleanup-reconciler"))


class ProbeSignalCleanupReconciler(Reconciler):
    name = "probe_cleanup"

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        super().__init__(
            interval_sec=CLEANUP_IDLE_WHEN_DISABLED_SEC,
            tick_lock=tick_lock,
            lock_ttl_sec=7200,
        )
        self._session_maker = AsyncDatabase.get_session_maker()

    async def _policy(self):
        async with self._session_maker() as session:
            policy = (await ProbePolicyRepository(session).list(limit=1))[0]
            await session.commit()
            return policy

    async def is_enabled(self) -> bool:
        return bool((await self._policy()).cleanup_enabled)

    async def interval_sec(self) -> int:
        return max(300, int((await self._policy()).cleanup_tick_sec))

    async def tick(self) -> int:
        return await self._execute_tick((await self._policy()).retention_days)

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
