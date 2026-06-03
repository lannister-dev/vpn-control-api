from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.entry.constants import AUTO_DRAIN_IDLE_WHEN_DISABLED_SEC
from services.entry.drain_service import EntryAutoDrainResult, EntryAutoDrainService
from services.nodes.policy.repository import NodePolicyRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("entry-auto-drain-reconciler"))


class EntryAutoDrainReconciler(Reconciler):
    name = "entry_auto_drain"

    def __init__(
        self,
        *,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        service_factory: Callable[[AsyncSession, object], EntryAutoDrainService] | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(
            interval_sec=AUTO_DRAIN_IDLE_WHEN_DISABLED_SEC,
            tick_lock=tick_lock,
            lock_ttl_sec=600,
        )
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._service_factory = service_factory or self._default_service_factory

    async def _policy(self):
        async with self._session_maker() as session:
            policy = (await NodePolicyRepository(session).list(limit=1))[0]
            await session.commit()
            return policy

    async def is_enabled(self) -> bool:
        return bool((await self._policy()).entry_auto_drain_enabled)

    async def interval_sec(self) -> int:
        return max(15, int((await self._policy()).entry_auto_drain_tick_sec))

    async def tick(self) -> EntryAutoDrainResult:
        return await self._execute_tick(await self._policy())

    async def _execute_tick(self, policy) -> EntryAutoDrainResult:
        async with self._session_maker() as session:
            service = self._service_factory(session, policy)
            result = await service.run()
            await session.commit()
            if (
                result.drained > 0
                or result.routes_blocked > 0
                or result.undrained > 0
                or result.routes_unblocked > 0
            ):
                logger.info(
                    "entry_auto_drain_tick",
                    processed=result.processed,
                    drained=result.drained,
                    undrained=result.undrained,
                    routes_blocked=result.routes_blocked,
                    routes_unblocked=result.routes_unblocked,
                    snapshots_enqueued=result.snapshots_enqueued,
                    skipped=result.skipped,
                )
            return result

    def _default_service_factory(self, session: AsyncSession, policy) -> EntryAutoDrainService:
        return EntryAutoDrainService(
            session=session,
            probe_failure_threshold=max(1, int(policy.entry_auto_drain_probe_failures)),
            drain_reason=policy.entry_auto_drain_reason or "entry_auto_drain",
            max_nodes=max(1, int(policy.entry_auto_drain_max_nodes)),
            auto_undrain_enabled=bool(policy.entry_auto_undrain_enabled),
            healthy_ticks_for_recovery=max(1, int(policy.entry_auto_undrain_healthy_ticks)),
        )
