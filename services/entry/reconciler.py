from __future__ import annotations

import asyncio
import logging
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.config import NodeAgentConfig, get_settings
from services.entry.drain_service import EntryAutoDrainResult, EntryAutoDrainService
from shared.database.session import AsyncDatabase
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("entry-auto-drain-reconciler"))


class EntryAutoDrainReconciler:
    def __init__(
        self,
        *,
        node_agent_settings: NodeAgentConfig | None = None,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        service_factory: Callable[[AsyncSession], EntryAutoDrainService] | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = node_agent_settings or get_settings().node_agent
        self._enabled = bool(getattr(settings, "entry_auto_drain_enabled", True))
        self._interval_sec = max(15, int(getattr(settings, "entry_auto_drain_tick_sec", 60)))
        self._probe_failures = max(1, int(getattr(settings, "entry_auto_drain_probe_failures", 3)))
        self._max_nodes = max(1, int(getattr(settings, "entry_auto_drain_max_nodes", 50)))
        self._reason = getattr(settings, "entry_auto_drain_reason", "entry_auto_drain")
        self._undrain_enabled = bool(getattr(settings, "entry_auto_undrain_enabled", True))
        self._healthy_ticks_for_recovery = max(1, int(getattr(settings, "entry_auto_undrain_healthy_ticks", 3)))

        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._service_factory = service_factory or self._default_service_factory
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:entry_auto_drain",
            ttl_sec=max(30, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("entry_auto_drain_disabled")
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

    async def run_once(self) -> EntryAutoDrainResult | None:
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
                logger.exception("entry_auto_drain_tick_failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self) -> EntryAutoDrainResult:
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return EntryAutoDrainResult(
                    processed=0, drained=0, routes_blocked=0,
                    snapshots_enqueued=0, skipped=0,
                )
            async with self._session_maker() as session:
                service = self._service_factory(session)
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

    def _default_service_factory(self, session: AsyncSession) -> EntryAutoDrainService:
        return EntryAutoDrainService(
            session=session,
            probe_failure_threshold=self._probe_failures,
            drain_reason=self._reason,
            max_nodes=self._max_nodes,
            auto_undrain_enabled=self._undrain_enabled,
            healthy_ticks_for_recovery=self._healthy_ticks_for_recovery,
        )
