from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.entry.constants import AUTO_DRAIN_IDLE_WHEN_DISABLED_SEC
from services.entry.drain_service import EntryAutoDrainResult, EntryAutoDrainService
from services.nodes.policy.repository import NodePolicyRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("entry-auto-drain-reconciler"))


class EntryAutoDrainReconciler:
    def __init__(
        self,
        *,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        service_factory: Callable[[AsyncSession, object], EntryAutoDrainService] | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._service_factory = service_factory or self._default_service_factory
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:entry_auto_drain",
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

    async def run_once(self) -> EntryAutoDrainResult | None:
        async with self._session_maker() as session:
            policy = (await NodePolicyRepository(session).list(limit=1))[0]
            await session.commit()
        if not policy.entry_auto_drain_enabled:
            return None
        return await self._execute_tick(policy)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            sleep_sec = AUTO_DRAIN_IDLE_WHEN_DISABLED_SEC
            try:
                async with self._session_maker() as session:
                    policy = (await NodePolicyRepository(session).list(limit=1))[0]
                    await session.commit()
                sleep_sec = max(15, int(policy.entry_auto_drain_tick_sec))
                if policy.entry_auto_drain_enabled:
                    await self._execute_tick(policy)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("entry_auto_drain_tick_failed")
            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self, policy) -> EntryAutoDrainResult:
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return EntryAutoDrainResult(
                    processed=0, drained=0, routes_blocked=0,
                    snapshots_enqueued=0, skipped=0,
                )
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
