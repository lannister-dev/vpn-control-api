from __future__ import annotations

import asyncio
import logging

from sqlalchemy import delete, select

from services.config import get_settings
from services.nodes.models import VpnNode
from services.vpn.subscriptions.models import SubscriptionRouteAssignment
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

_ENTRY_ROLES = ("entry", "whitelist_entry")


class SubscriptionAssignmentInvalidator:
    """Deletes subscription_route_assignment rows that point to a vpn_node
    whose role no longer matches an entry role. After a role swap (entry →
    backend) cached pins survive and clients keep dialing the wrong server;
    this reconciler cleans them up so the next subscription poll re-picks a
    valid entry.
    """

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._interval_sec = max(60, get_settings().routes.warmup_tick_sec)
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:subscription_assignment_invalidator",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._log = StructuredLogger(logging.getLogger("subscription-assignment-invalidator"))

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
                self._log.exception("subscription_assignment_invalidator_tick_failed")
            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        async with self._session_maker() as session:
            stale_ids = (
                select(VpnNode.id).where(VpnNode.role.notin_(_ENTRY_ROLES))
            ).scalar_subquery()
            stmt = delete(SubscriptionRouteAssignment).where(
                SubscriptionRouteAssignment.entry_node_id.in_(stale_ids)
            )
            result = await session.execute(stmt)
            deleted = result.rowcount or 0
            if deleted:
                await session.commit()
                self._log.info("subscription_assignment_invalidated", deleted=deleted)
            return deleted
