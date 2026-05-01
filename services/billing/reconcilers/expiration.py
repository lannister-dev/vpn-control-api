from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from services.billing.repository import OrderRepository
from services.config import BillingConfig, get_settings
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import BILLING_ORDER_TOTAL
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("billing-order-expiration-reconciler"))


class BillingOrderExpirationReconciler:
    def __init__(
        self,
        *,
        billing_settings: BillingConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = billing_settings or get_settings().billing
        self._enabled = bool(getattr(settings, "expiration_reconciler_enabled", True))
        self._interval_sec = max(30, int(getattr(settings, "expiration_tick_sec", 60)))
        self._batch_size = max(1, int(getattr(settings, "expiration_batch_size", 500)))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:billing_order_expiration",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._task is not None and not self._task.done():
            return
        if not self._enabled:
            logger.info("billing_order_expiration_disabled")
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
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

    async def _run(self):
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("billing_order_expiration_tick_failed")

            watchdog.heartbeat(
                self.__class__.__name__,
                max_silence_sec=self._interval_sec * 2 + 60,
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _execute_tick(self) -> int:
        async with self._session_maker() as session:
            repo = OrderRepository(session)
            now = datetime.now(timezone.utc)
            count = await repo.bulk_expire_pending(now=now, limit=self._batch_size)
            if count:
                await session.commit()
                BILLING_ORDER_TOTAL.labels(provider="any", status="expired").inc(count)
                logger.info("billing_orders_expired", count=count)
            return count
