from __future__ import annotations

import logging

from services.traffic.policy.constants import CLEANUP_IDLE_WHEN_DISABLED_SEC
from services.traffic.policy.repository import TrafficPolicyRepository
from services.traffic.users.service import UserTrafficService
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("traffic-cleanup-reconciler"))


class TrafficHistoryCleanupReconciler(Reconciler):
    name = "traffic_cleanup"

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        super().__init__(
            interval_sec=CLEANUP_IDLE_WHEN_DISABLED_SEC,
            tick_lock=tick_lock,
            lock_ttl_sec=7200,
        )
        self._session_maker = AsyncDatabase.get_session_maker()

    async def _policy(self):
        async with self._session_maker() as session:
            policy = (await TrafficPolicyRepository(session).list(limit=1))[0]
            await session.commit()
            return policy

    async def is_enabled(self) -> bool:
        return bool((await self._policy()).user_cleanup_enabled)

    async def interval_sec(self) -> int:
        return max(CLEANUP_IDLE_WHEN_DISABLED_SEC, int((await self._policy()).user_cleanup_tick_sec))

    async def tick(self) -> int:
        return await self._execute_tick((await self._policy()).user_retention_days)

    async def _execute_tick(self, retention_days: int) -> int:
        async with self._session_maker() as session:
            deleted = await UserTrafficService(session).cleanup_history(
                retention_days=retention_days,
            )
            await session.commit()
            if deleted > 0:
                logger.info(
                    "traffic_cleanup_tick",
                    deleted=deleted,
                    retention_days=int(retention_days),
                )
            return deleted
