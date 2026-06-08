from __future__ import annotations

import functools
import logging
import time
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import NodeAgentState, VpnNode
from services.nodes.policy.repository import NodePolicyRepository
from services.placements.constants import REBALANCE_IDLE_WHEN_DISABLED_SEC
from services.placements.repository import UserPlacementRepository
from services.placements.transport import NodeAgentPlacementTransport
from services.routes.models import Route
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import (
    PLACEMENT_REBALANCE_MISSING_GAUGE,
    PLACEMENT_REBALANCE_TOTAL,
)
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("placement-rebalance-reconciler"))


class PlacementRebalanceReconciler(Reconciler):
    name = "placement_rebalance"

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        super().__init__(
            interval_sec=REBALANCE_IDLE_WHEN_DISABLED_SEC,
            tick_lock=tick_lock,
            lock_ttl_sec=600,
        )
        self._session_maker = AsyncDatabase.get_session_maker()

    async def _policy(self):
        async with self._session_maker() as session:
            policy = (await NodePolicyRepository(session).list(limit=1))[0]
            await session.commit()
            return policy

    async def is_enabled(self) -> bool:
        return bool((await self._policy()).placement_rebalance_enabled)

    async def interval_sec(self) -> int:
        return max(30, int((await self._policy()).placement_rebalance_tick_sec))

    async def tick(self) -> int:
        return await self._execute_tick(await self._policy())

    async def _execute_tick(self, policy) -> int:
        batch_size = max(1, int(policy.placement_rebalance_batch_size))
        stale_after_sec = max(30, int(policy.stale_after_sec))
        async with self._session_maker() as session:
            transport = NodeAgentPlacementTransport(session)
            drained_ids = await self._deactivate_placements_on_draining_backends(session)
            if drained_ids:
                await transport.enqueue_for_placement_ids(drained_ids)
                logger.info(
                    "placement_drain_deactivated",
                    placement_ids=len(drained_ids),
                )

            healthy_node_ids = await self._find_healthy_backend_node_ids(session, stale_after_sec)
            if len(healthy_node_ids) < 2:
                if drained_ids:
                    await session.commit()
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

    async def _deactivate_placements_on_draining_backends(
        self, session: AsyncSession,
    ) -> list[UUID]:
        result = await session.execute(text("""
            UPDATE user_placement up
            SET desired_state = 'inactive',
                op_version = up.op_version + 1,
                last_migration_reason = 'backend_draining',
                updated_at = now()
            FROM vpn_node vn
            WHERE vn.id = up.backend_node_id
              AND vn.is_draining = true
              AND up.desired_state = 'active'
              AND up.is_active = true
            RETURNING up.id
        """))
        return [row[0] for row in result.all()]

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
                exists().where(
                    Route.node_id == VpnNode.id,
                    Route.entry_node_id.is_not(None),
                ),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


# def decorator(func):
#     @functools.wraps(func)
#     def wrapper(*args, **kwargs):
#         time.
#
#
#
# @decorator
# def example(param):
#     return
