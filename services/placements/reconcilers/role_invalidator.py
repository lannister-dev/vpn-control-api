from __future__ import annotations

import asyncio
import logging

from services.config import get_settings
from services.placements.repository import UserPlacementRepository
from services.placements.transport import NodeAgentPlacementTransport
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger


class PlacementNodeRoleInvalidator:
    """Periodically deactivates active user_placement rows whose backend_node_id
    points to a vpn_node that is no longer in 'backend' role.

    Why: when a node is role-swapped (e.g. backend → entry), the placements that
    used to live on it survive in the DB. A later subscription.activate or
    rebalance touch flips them back to desired=active, which then fans out via
    placement_command — the (now entry) target node fails to render because
    its own id is not in the BackendRegistry, and the user has no working route.

    What: marks the affected rows desired=inactive, is_active=false, bumps
    op_version, and enqueues placement_command updates so any agent that still
    holds them in its store transitions cleanly to inactive.
    """

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._interval_sec = max(60, get_settings().routes.warmup_tick_sec)
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:placement_node_role_invalidator",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._log = StructuredLogger(logging.getLogger("placement-node-role-invalidator"))

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
                self._log.exception("placement_node_role_invalidator_tick_failed")
            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        async with self._session_maker() as session:
            repo = UserPlacementRepository(session)
            placement_ids = await repo.deactivate_placements_on_non_backend_nodes()
            if not placement_ids:
                return 0
            transport = NodeAgentPlacementTransport(session)
            await transport.enqueue_for_placement_ids(placement_ids)
            await session.commit()
            self._log.info(
                "placement_node_role_invalidated",
                deactivated=len(placement_ids),
            )
            return len(placement_ids)
