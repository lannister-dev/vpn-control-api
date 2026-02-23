from __future__ import annotations

import asyncio
import logging
from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.config import ProbeConfig, get_settings
from services.nodes.repository import VpnNodeRepository
from services.placements.service import UserPlacementService
from services.probe.drain_service import ProbeDrainService
from services.probe.repository import ProbeSignalRepository
from services.probe.schemas import ProbeAutoDrainMigrateIn, ProbeAutoDrainMigrateOut
from shared.database.session import AsyncDatabase
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("probe-auto-drain-reconciler"))


class ProbeAutoDrainReconciler:
    def __init__(
            self,
            *,
            probe_settings: ProbeConfig | None = None,
            session_maker: async_sessionmaker[AsyncSession] | None = None,
            service_factory: Callable[[AsyncSession], ProbeDrainService] | None = None,
            tick_lock: RedisTickLock | None = None,
    ):
        settings = probe_settings or get_settings().probe

        self._enabled = bool(settings.auto_drain_migrate_enabled)
        self._interval_sec = max(30, int(settings.auto_drain_tick_sec))
        self._payload = self._build_payload(settings)

        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._service_factory = service_factory or self._default_service_factory
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:probe_auto_drain",
            ttl_sec=max(30, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("probe_auto_drain_disabled")
            return
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
        if not self._enabled:
            return None
        return await self._execute_tick()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._execute_tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("probe_auto_drain_tick_failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self) -> ProbeAutoDrainMigrateOut:
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return ProbeAutoDrainMigrateOut(
                    processed=0,
                    migrated=0,
                    skipped=0,
                    dry_run=False,
                    items=[],
                )
            async with self._session_maker() as session:
                service = self._service_factory(session)
                result = await service.auto_drain_and_migrate_backends(self._payload)
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

    def _build_payload(self, settings: ProbeConfig) -> ProbeAutoDrainMigrateIn:
        raw_target_backend_id = (settings.auto_drain_target_backend_id or "").strip()
        target_backend_id: UUID | None = None
        if raw_target_backend_id:
            try:
                target_backend_id = UUID(raw_target_backend_id)
            except ValueError:
                logger.warning(
                    "probe_auto_drain_invalid_target_backend_id",
                    target_backend_id=raw_target_backend_id,
                )

        source = (settings.auto_drain_source or "").strip() or None
        reason = (settings.auto_drain_last_migration_reason or "").strip() or "probe_auto_failure"

        return ProbeAutoDrainMigrateIn(
            target_backend_id=target_backend_id,
            source=source,
            require_recent_failure=bool(settings.auto_drain_require_recent_failure),
            max_probe_age_sec=max(30, int(settings.auto_drain_max_probe_age_sec)),
            min_consecutive_failures=max(1, int(settings.auto_drain_min_consecutive_failures)),
            include_already_draining=bool(settings.auto_drain_include_already_draining),
            dry_run=False,
            max_nodes=min(200, max(1, int(settings.auto_drain_max_nodes))),
            last_migration_reason=reason,
        )

    @staticmethod
    def _default_service_factory(session: AsyncSession) -> ProbeDrainService:
        return ProbeDrainService(
            node_repository=VpnNodeRepository(session),
            probe_repository=ProbeSignalRepository(session),
            placement_service=UserPlacementService(session),
        )
