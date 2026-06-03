from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.placements.service import UserPlacementService
from services.probe.constants import AUTO_DRAIN_IDLE_WHEN_DISABLED_SEC
from services.probe.drain_service import ProbeDrainService
from services.probe.policy.repository import ProbePolicyRepository
from services.probe.repository import ProbeSignalRepository
from services.probe.schemas import ProbeAutoDrainMigrateIn, ProbeAutoDrainMigrateOut
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("probe-auto-drain-reconciler"))


class ProbeAutoDrainReconciler(Reconciler):
    name = "probe_auto_drain"

    def __init__(
            self,
            *,
            session_maker: async_sessionmaker[AsyncSession] | None = None,
            service_factory: Callable[[AsyncSession], ProbeDrainService] | None = None,
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
            policy = (await ProbePolicyRepository(session).list(limit=1))[0]
            await session.commit()
            return policy

    async def is_enabled(self) -> bool:
        return bool((await self._policy()).auto_drain_enabled)

    async def interval_sec(self) -> int:
        return max(30, int((await self._policy()).auto_drain_tick_sec))

    async def tick(self) -> ProbeAutoDrainMigrateOut:
        return await self._execute_tick(await self._policy())

    async def _execute_tick(self, policy) -> ProbeAutoDrainMigrateOut:
        payload = self._build_payload(policy)
        async with self._session_maker() as session:
            service = self._service_factory(session)
            result = await service.auto_drain_and_migrate_backends(payload)
            await session.commit()
            if result.processed > 0:
                logger.info(
                    "probe_auto_drain_tick",
                    processed=result.processed,
                    migrated=result.migrated,
                    skipped=result.skipped,
                    dry_run=result.dry_run,
                )
            return result

    def _build_payload(self, policy) -> ProbeAutoDrainMigrateIn:
        return ProbeAutoDrainMigrateIn(
            target_backend_id=policy.auto_drain_target_backend_id,
            source=policy.auto_drain_source or None,
            require_recent_failure=bool(policy.auto_drain_require_recent_failure),
            max_probe_age_sec=max(30, int(policy.auto_drain_max_probe_age_sec)),
            min_consecutive_failures=max(1, int(policy.auto_drain_min_consecutive_failures)),
            include_already_draining=bool(policy.auto_drain_include_already_draining),
            dry_run=False,
            max_nodes=min(500, max(1, int(policy.auto_drain_max_nodes))),
            last_migration_reason=policy.auto_drain_last_migration_reason or "probe_auto_failure",
        )

    @staticmethod
    def _default_service_factory(session: AsyncSession) -> ProbeDrainService:
        return ProbeDrainService(
            node_repository=VpnNodeRepository(session),
            probe_repository=ProbeSignalRepository(session),
            placement_service=UserPlacementService(session),
            node_state_repository=NodeAgentStateRepository(session),
        )
