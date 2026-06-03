from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.nodes.auto_heal_service import NodeAutoHealTickOut, NodePlacementAutoHealService
from services.nodes.constants import PLACEMENT_RECONCILER_IDLE_WHEN_DISABLED_SEC
from services.nodes.policy.repository import NodePolicyRepository
from services.notifications.service import NotificationService
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("node-auto-heal-reconciler"))


class NodePlacementReconciler(Reconciler):
    name = "node_auto_heal"

    def __init__(
        self,
        *,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        service_factory: Callable[[AsyncSession, int, int, bool, int], NodePlacementAutoHealService] | None = None,
        tick_lock: RedisTickLock | None = None,
        notifications: NotificationService | None = None,
    ):
        super().__init__(
            interval_sec=PLACEMENT_RECONCILER_IDLE_WHEN_DISABLED_SEC,
            tick_lock=tick_lock,
            lock_ttl_sec=600,
        )
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._notifications = notifications
        self._service_factory = service_factory or self._default_service_factory

    async def _policy(self):
        async with self._session_maker() as session:
            policy = (await NodePolicyRepository(session).list(limit=1))[0]
            await session.commit()
            return policy

    async def is_enabled(self) -> bool:
        return bool((await self._policy()).auto_heal_enabled)

    async def interval_sec(self) -> int:
        return max(30, int((await self._policy()).auto_heal_tick_sec))

    async def tick(self) -> NodeAutoHealTickOut:
        return await self._execute_tick(await self._policy())

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
