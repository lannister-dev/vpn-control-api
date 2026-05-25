from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.nodes.auto_heal_service import NodeAutoHealTickOut, NodePlacementAutoHealService
from services.nodes.constants import PLACEMENT_RECONCILER_IDLE_WHEN_DISABLED_SEC
from services.nodes.policy.repository import NodePolicyRepository
from services.notifications.service import NotificationService
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("node-auto-heal-reconciler"))


class NodePlacementReconciler:
    def __init__(
        self,
        *,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        service_factory: Callable[[AsyncSession, int, int, bool, int], NodePlacementAutoHealService] | None = None,
        tick_lock: RedisTickLock | None = None,
        notifications: NotificationService | None = None,
    ):
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._notifications = notifications
        self._service_factory = service_factory or self._default_service_factory
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:node_auto_heal",
            ttl_sec=600,
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def run_once(self) -> NodeAutoHealTickOut | None:
        async with self._session_maker() as session:
            policy = (await NodePolicyRepository(session).list(limit=1))[0]
            await session.commit()
        if not policy.auto_heal_enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                logger.debug("node_auto_heal_lock_not_acquired")
                return NodeAutoHealTickOut()
            return await self._execute_tick(policy)

    async def _run(self) -> None:
        logger.info("node_auto_heal_loop_started")
        while not self._stop_event.is_set():
            sleep_sec = PLACEMENT_RECONCILER_IDLE_WHEN_DISABLED_SEC
            try:
                async with self._session_maker() as session:
                    policy = (await NodePolicyRepository(session).list(limit=1))[0]
                    await session.commit()
                sleep_sec = max(30, int(policy.auto_heal_tick_sec))
                if policy.auto_heal_enabled:
                    async with self._tick_lock.hold() as acquired:
                        if acquired:
                            await self._execute_tick(policy)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("node_auto_heal_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self, policy) -> NodeAutoHealTickOut:
        async with self._session_maker() as session:
            service = self._service_factory(
                session,
                max(30, int(policy.stale_after_sec)),
                min(500, max(1, int(policy.auto_heal_max_nodes))),
                bool(policy.auto_undrain_enabled),
                max(0, int(policy.auto_heal_drain_cooldown_sec)),
            )
            out = await service.run_once()
            await session.commit()
            logger.info(
                "node_auto_heal_tick",
                processed_nodes=out.processed_nodes,
                drained_nodes=out.drained_nodes,
                migrated_nodes=out.migrated_nodes,
                migrated_placements=out.migrated_placements,
                skipped_nodes=out.skipped_nodes,
                undrained_nodes=out.undrained_nodes,
                orphan_active_placements=out.orphan_active_placements,
            )
            return out

    def _default_service_factory(
        self,
        session: AsyncSession,
        stale_after_sec: int,
        max_nodes: int,
        auto_undrain_enabled: bool,
        drain_cooldown_sec: int = 180,
    ) -> NodePlacementAutoHealService:
        return NodePlacementAutoHealService(
            session,
            stale_after_sec=stale_after_sec,
            max_nodes=max_nodes,
            auto_undrain_enabled=auto_undrain_enabled,
            drain_cooldown_sec=drain_cooldown_sec,
            notifications=self._notifications,
        )
