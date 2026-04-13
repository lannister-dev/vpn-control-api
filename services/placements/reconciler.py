from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import NodeAgentConfig, get_settings
from services.nodes.models import NodeAgentState, VpnNode
from services.placements.repository import UserPlacementRepository
from services.placements.transport import NodeAgentPlacementTransport
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import (
    PLACEMENT_REBALANCE_MISSING_GAUGE,
    PLACEMENT_REBALANCE_TOTAL,
)
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("placement-rebalance-reconciler"))


class PlacementRebalanceReconciler:
    """Ensures every active VPN key has placements on ALL healthy backend nodes.

    After a node recovers from failure, auto_heal un-drains it but does not
    restore the placements that were migrated away. This reconciler detects
    missing (key_id, node_id) pairs and creates them via bulk upsert.
    """

    def __init__(
        self,
        *,
        node_agent_settings: NodeAgentConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = node_agent_settings or get_settings().node_agent
        self._enabled = bool(settings.placement_rebalance_enabled)
        self._interval_sec = max(30, int(settings.placement_rebalance_tick_sec))
        self._batch_size = max(1, int(settings.placement_rebalance_batch_size))
        self._stale_after_sec = max(30, int(settings.stale_after_sec))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:placement_rebalance",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("placement_rebalance_disabled")
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

    async def run_once(self) -> int | None:
        if not self._enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._execute_tick()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("placement_rebalance_tick_failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_sec
                )
            except TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        async with self._session_maker() as session:
            healthy_node_ids = await self._find_healthy_backend_node_ids(session)
            if len(healthy_node_ids) < 2:
                return 0

            placement_repo = UserPlacementRepository(session)
            missing_pairs = await placement_repo.find_missing_placements(
                healthy_node_ids=healthy_node_ids,
                batch_size=self._batch_size,
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
        self, session: AsyncSession,
    ) -> list[UUID]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self._stale_after_sec)

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
