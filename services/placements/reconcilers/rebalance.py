from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import NodeAgentState, VpnNode
from services.nodes.policy.repository import NodePolicyRepository
from services.placements.repository import UserPlacementRepository
from services.placements.transport import NodeAgentPlacementTransport
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.monitoring.metrics import (
    PLACEMENT_REBALANCE_MISSING_GAUGE,
    PLACEMENT_REBALANCE_TOTAL,
)
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("placement-rebalance-reconciler"))


class PlacementRebalanceReconciler:
    """Ensures every active VPN key has placements on ALL healthy backend nodes.

    Reads placement_rebalance_* / stale_after_sec from NodePolicy on every tick.
    """

    _IDLE_WHEN_DISABLED_SEC = 120

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:placement_rebalance",
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

    async def run_once(self) -> int | None:
        async with self._session_maker() as session:
            policy = await NodePolicyRepository(session).get_current()
            await session.commit()
        if not policy.placement_rebalance_enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._execute_tick(policy)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            sleep_sec = self._IDLE_WHEN_DISABLED_SEC
            try:
                async with self._session_maker() as session:
                    policy = await NodePolicyRepository(session).get_current()
                    await session.commit()
                sleep_sec = max(30, int(policy.placement_rebalance_tick_sec))
                if policy.placement_rebalance_enabled:
                    async with self._tick_lock.hold() as acquired:
                        if acquired:
                            await self._execute_tick(policy)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("placement_rebalance_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self, policy) -> int:
        batch_size = max(1, int(policy.placement_rebalance_batch_size))
        stale_after_sec = max(30, int(policy.stale_after_sec))
        async with self._session_maker() as session:
            healthy_node_ids = await self._find_healthy_backend_node_ids(session, stale_after_sec)
            if len(healthy_node_ids) < 2:
                return 0

            placement_repo = UserPlacementRepository(session)
            missing_pairs = await placement_repo.find_missing_placements(
                healthy_node_ids=healthy_node_ids,
                batch_size=batch_size,
            )

            PLACEMENT_REBALANCE_MISSING_GAUGE.set(len(missing_pairs))

            if not missing_pairs:
                return 0

            created_ids = await placement_repo.bulk_upsert_set_pending(
                pairs=missing_pairs,
                desired_state="active",
                last_migration_reason="rebalance",
            )

            if created_ids:
                transport = NodeAgentPlacementTransport(session)
                await transport.enqueue_for_placement_ids(created_ids)

            await session.commit()

            PLACEMENT_REBALANCE_TOTAL.labels(result="ok").inc(len(created_ids))
            logger.info(
                "placement_rebalance_tick",
                missing_found=len(missing_pairs),
                created=len(created_ids),
                healthy_nodes=len(healthy_node_ids),
            )
            return len(created_ids)

    async def _find_healthy_backend_node_ids(
        self, session: AsyncSession, stale_after_sec: int,
    ) -> list[UUID]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=stale_after_sec)

        stmt = (
            select(VpnNode.id)
            .join(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .where(
                VpnNode.is_active.is_(True),
                VpnNode.is_enabled.is_(True),
                VpnNode.is_draining.is_(False),
                VpnNode.role == "backend",
                NodeAgentState.is_healthy.is_(True),
                NodeAgentState.last_seen_at >= cutoff,
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
