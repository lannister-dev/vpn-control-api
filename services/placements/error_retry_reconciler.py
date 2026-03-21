from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update as sa_update

from services.config import NodeAgentConfig, get_settings
from services.placements.model import UserPlacement
from services.placements.transport import NodeAgentPlacementTransport
from shared.database.session import AsyncDatabase
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("placement-error-retry-reconciler"))


class PlacementErrorRetryReconciler:
    """Re-queues placements stuck in 'error' or stale 'pending' state.

    - error: resets to pending, bumps op_version, creates outbox entries.
    - stale pending: outbox entry was lost (e.g. NATS timeout during deploy),
      re-creates outbox entries without changing state.
    """

    def __init__(
        self,
        *,
        node_agent_settings: NodeAgentConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = node_agent_settings or get_settings().node_agent
        self._enabled = bool(settings.placement_error_retry_enabled)
        self._interval_sec = max(30, int(settings.placement_error_retry_tick_sec))
        self._retry_after_sec = max(30, int(settings.placement_error_retry_after_sec))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:placement_error_retry",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._enabled:
            logger.info("placement_error_retry_disabled")
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
                logger.exception("placement_error_retry_tick_failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._retry_after_sec)
        total = 0
        async with self._session_maker() as session:
            transport = NodeAgentPlacementTransport(session)

            # 1) Error placements → reset to pending + bump op_version + outbox
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
                logger.info(
                    "placement_error_retry",
                    retried=len(error_ids),
                )

            # 2) Stale pending placements → re-create outbox entries
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
                logger.info(
                    "placement_stale_pending_retry",
                    retried=len(pending_ids),
                )

            if total > 0:
                await session.commit()

            return total
