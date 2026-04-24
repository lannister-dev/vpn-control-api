from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update as sa_update

from services.nodes.policy.repository import NodePolicyRepository
from services.placements.model import UserPlacement
from services.placements.transport import NodeAgentPlacementTransport
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("placement-error-retry-reconciler"))


class PlacementErrorRetryReconciler:
    """Re-queues placements stuck in 'error' or stale 'pending' state.

    Reads placement_error_retry_* from NodePolicy on every tick.
    """

    _IDLE_WHEN_DISABLED_SEC = 120

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:placement_error_retry",
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
        if not policy.placement_error_retry_enabled:
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
                sleep_sec = max(30, int(policy.placement_error_retry_tick_sec))
                if policy.placement_error_retry_enabled:
                    async with self._tick_lock.hold() as acquired:
                        if acquired:
                            await self._execute_tick(policy)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("placement_error_retry_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except TimeoutError:
                continue

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
