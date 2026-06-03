from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.billing.repository import OrderRepository
from services.config import BillingConfig, get_settings
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import BILLING_ORDER_TOTAL
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("billing-order-expiration-reconciler"))


class BillingOrderExpirationReconciler(Reconciler):
    name = "billing_order_expiration"

    def __init__(
        self,
        *,
        billing_settings: BillingConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ):
        settings = billing_settings or get_settings().billing
        super().__init__(
            interval_sec=max(30, int(getattr(settings, "expiration_tick_sec", 60))),
            enabled=bool(getattr(settings, "expiration_reconciler_enabled", True)),
            tick_lock=tick_lock,
        )
        self._batch_size = max(1, int(getattr(settings, "expiration_batch_size", 500)))
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
        async with self._session_maker() as session:
            repo = OrderRepository(session)
            now = datetime.now(timezone.utc)
            count = await repo.bulk_expire_pending(now=now, limit=self._batch_size)
            if count:
                await session.commit()
                BILLING_ORDER_TOTAL.labels(provider="any", status="expired").inc(count)
                logger.info("billing_orders_expired", count=count)
            return count
