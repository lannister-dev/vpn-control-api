from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy import update as sa_update

from services.nodes.policy.repository import NodePolicyRepository
from services.placements.constants import ERROR_RETRY_IDLE_WHEN_DISABLED_SEC
from services.placements.models import UserPlacement
from services.placements.transport import NodeAgentPlacementTransport
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("placement-error-retry-reconciler"))


class PlacementErrorRetryReconciler(Reconciler):
    name = "placement_error_retry"

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        super().__init__(
            interval_sec=ERROR_RETRY_IDLE_WHEN_DISABLED_SEC,
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
        return bool((await self._policy()).placement_error_retry_enabled)

    async def interval_sec(self) -> int:
        return max(30, int((await self._policy()).placement_error_retry_tick_sec))

    async def tick(self) -> int:
        return await self._execute_tick(await self._policy())

    async def _execute_tick(self, policy) -> int:
        retry_after_sec = max(30, int(policy.placement_error_retry_after_sec))
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=retry_after_sec)
        total = 0
        async with self._session_maker() as session:
            transport = NodeAgentPlacementTransport(session)

            error_stmt = (
                select(UserPlacement.id)
                .where(UserPlacement.applied_state == "error")
                .where(UserPlacement.is_active.is_(True))
                .where(UserPlacement.updated_at < cutoff)
            )
            error_ids = list((await session.execute(error_stmt)).scalars().all())

            if error_ids:
                await session.execute(
                    sa_update(UserPlacement)
                    .where(UserPlacement.id.in_(error_ids))
                    .values(
                        applied_state="pending",
                        op_version=UserPlacement.op_version + 1,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await transport.enqueue_for_placement_ids(error_ids)
                total += len(error_ids)
                logger.info("placement_error_retry", retried=len(error_ids))

            pending_stmt = (
                select(UserPlacement.id)
                .where(UserPlacement.applied_state == "pending")
                .where(UserPlacement.is_active.is_(True))
                .where(UserPlacement.updated_at < cutoff)
            )
            pending_ids = list((await session.execute(pending_stmt)).scalars().all())

            if pending_ids:
                await transport.enqueue_for_placement_ids(pending_ids)
                total += len(pending_ids)
                logger.info("placement_stale_pending_retry", retried=len(pending_ids))

            if total > 0:
                await session.commit()

            return total
