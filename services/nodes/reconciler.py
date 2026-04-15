from __future__ import annotations

import asyncio
import logging
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.config import NodeAgentConfig, get_settings
from services.nodes.auto_heal_service import NodeAutoHealTickOut, NodePlacementAutoHealService
from shared.database.session import AsyncDatabase
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("node-auto-heal-reconciler"))


class NodePlacementReconciler:
    def __init__(
        self,
        *,
        node_settings: NodeAgentConfig | None = None,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        service_factory: Callable[[AsyncSession, int, int, bool, int], NodePlacementAutoHealService] | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = node_settings or get_settings().node_agent

        self._enabled = bool(settings.auto_heal_enabled)
        self._interval_sec = max(30, int(settings.auto_heal_tick_sec))
        self._stale_after_sec = max(30, int(settings.stale_after_sec))
        self._max_nodes = min(500, max(1, int(settings.auto_heal_max_nodes)))
        self._auto_undrain_enabled = bool(settings.auto_undrain_enabled)
        self._drain_cooldown_sec = max(0, int(settings.auto_heal_drain_cooldown_sec))

        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._service_factory = service_factory or self._default_service_factory
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:node_auto_heal",
            ttl_sec=max(30, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("node_auto_heal_disabled")
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

    async def run_once(self) -> NodeAutoHealTickOut | None:
        if not self._enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                logger.debug("node_auto_heal_lock_not_acquired")
                return NodeAutoHealTickOut()
            return await self._execute_tick()

    async def _run(self) -> None:
        logger.info("node_auto_heal_loop_started")
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("node_auto_heal_tick_failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self) -> NodeAutoHealTickOut:
        logger.info("node_auto_heal_tick_start")
        async with self._session_maker() as session:
            service = self._service_factory(
                session,
                self._stale_after_sec,
                self._max_nodes,
                self._auto_undrain_enabled,
                self._drain_cooldown_sec,
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

    @staticmethod
    def _default_service_factory(
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
        )
