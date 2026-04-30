from __future__ import annotations

import asyncio
import logging

from services.traffic.nodes.service import NodeTrafficService
from services.traffic.policy.constants import CLEANUP_IDLE_WHEN_DISABLED_SEC
from services.traffic.policy.repository import TrafficPolicyRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("node-traffic-cleanup-reconciler"))


class NodeTrafficHistoryCleanupReconciler:
    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:node_traffic_cleanup",
            ttl_sec=7200,
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
            policy = (await TrafficPolicyRepository(session).list(limit=1))[0]
            await session.commit()
        if not policy.node_cleanup_enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._execute_tick(policy.node_retention_days)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            sleep_sec = CLEANUP_IDLE_WHEN_DISABLED_SEC
            try:
                async with self._session_maker() as session:
                    policy = (await TrafficPolicyRepository(session).list(limit=1))[0]
                    await session.commit()
                sleep_sec = max(CLEANUP_IDLE_WHEN_DISABLED_SEC, int(policy.node_cleanup_tick_sec))
                if policy.node_cleanup_enabled:
                    async with self._tick_lock.hold() as acquired:
                        if acquired:
                            await self._execute_tick(policy.node_retention_days)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("node_traffic_cleanup_tick_failed")

            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=sleep_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self, retention_days: int) -> int:
        async with self._session_maker() as session:
            deleted = await NodeTrafficService(session).cleanup_history(
                retention_days=retention_days,
            )
            await session.commit()
            if deleted > 0:
                logger.info(
                    "node_traffic_cleanup_tick",
                    deleted=deleted,
                    retention_days=int(retention_days),
                )
            return deleted
