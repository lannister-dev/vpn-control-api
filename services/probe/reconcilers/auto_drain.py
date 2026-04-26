from __future__ import annotations

import asyncio
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
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("probe-auto-drain-reconciler"))


class ProbeAutoDrainReconciler:
    def __init__(
            self,
            *,
            session_maker: async_sessionmaker[AsyncSession] | None = None,
            service_factory: Callable[[AsyncSession], ProbeDrainService] | None = None,
            tick_lock: RedisTickLock | None = None,
    ):
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._service_factory = service_factory or self._default_service_factory
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:probe_auto_drain",
            ttl_sec=600,
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def run_once(self) -> ProbeAutoDrainMigrateOut | None:
        async with self._session_maker() as session:
            policy = (await ProbePolicyRepository(session).list(limit=1))[0]
            await session.commit()
            if not policy.auto_drain_enabled:
                return None
        return await self._execute_tick(policy)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            sleep_sec = AUTO_DRAIN_IDLE_WHEN_DISABLED_SEC
            try:
                async with self._session_maker() as session:
                    policy = (await ProbePolicyRepository(session).list(limit=1))[0]
                    await session.commit()
                sleep_sec = max(30, int(policy.auto_drain_tick_sec))
                if policy.auto_drain_enabled:
                    await self._execute_tick(policy)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("probe_auto_drain_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self, policy) -> ProbeAutoDrainMigrateOut:
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return ProbeAutoDrainMigrateOut(
                    processed=0,
                    migrated=0,
                    skipped=0,
                    dry_run=False,
                    items=[],
                )
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
