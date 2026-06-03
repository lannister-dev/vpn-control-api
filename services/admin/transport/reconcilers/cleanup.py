from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from services.admin.transport.constants import (
    CLEANUP_IDLE_WHEN_DISABLED_SEC,
    NATS_DEDUP_RETENTION_HOURS,
)
from services.admin.transport.policy.repository import TransportPolicyRepository
from services.admin.transport.repository import AdminTransportRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("transport-cleanup-reconciler"))


class AdminTransportCleanupReconciler(Reconciler):
    name = "transport_cleanup"

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        super().__init__(
            interval_sec=CLEANUP_IDLE_WHEN_DISABLED_SEC,
            tick_lock=tick_lock,
            lock_ttl_sec=7200,
        )
        self._session_maker = AsyncDatabase.get_session_maker()

    async def _policy(self):
        async with self._session_maker() as session:
            policy = (await TransportPolicyRepository(session).list(limit=1))[0]
            await session.commit()
            return policy

    async def is_enabled(self) -> bool:
        return bool((await self._policy()).cleanup_enabled)

    async def interval_sec(self) -> int:
        return max(CLEANUP_IDLE_WHEN_DISABLED_SEC, int((await self._policy()).cleanup_tick_sec))

    async def tick(self) -> tuple[int, int, int]:
        return await self._execute_tick((await self._policy()).retention_days)

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
