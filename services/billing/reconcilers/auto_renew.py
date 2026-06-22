from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from services.billing.exceptions import InsufficientBalance
from services.billing.schemas import (
    OrderCreateIn,
    OrderTypeEnum,
    PaymentProviderEnum,
)
from services.billing.service import BillingService
from services.vpn.subscriptions.models import Subscription
from services.vpn.subscriptions.repository import SubscriptionRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.client import redis_client
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("auto-renew-reconciler"))

AUTO_RENEW_WINDOW_SEC = 24 * 3600
AUTO_RENEW_INTERVAL_SEC = 300


class AutoRenewReconciler(Reconciler):
    name = "auto_renew"

    def __init__(
        self,
        *,
        interval_sec: int = AUTO_RENEW_INTERVAL_SEC,
        window_sec: int = AUTO_RENEW_WINDOW_SEC,
        batch_size: int = 200,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(interval_sec=max(60, int(interval_sec)), tick_lock=tick_lock)
        self._window_sec = int(window_sec)
        self._batch_size = max(1, int(batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
        async with self._session_maker() as session:
            now = datetime.now(timezone.utc)
            window_end = now + timedelta(seconds=self._window_sec)
            due = await SubscriptionRepository(session).list_due_auto_renew(
                now=now, window_end=window_end, limit=self._batch_size
            )
        if not due:
            return 0

        renewed = 0
        for sub in due:
            async with self._session_maker() as session:
                billing = BillingService(session, redis=redis_client)
                if await self._renew_one(billing, sub):
                    renewed += 1
        if renewed:
            logger.info("auto_renew_done", renewed=renewed)
        return renewed

    async def _renew_one(self, billing: BillingService, sub: Subscription) -> bool:
        try:
            preview = await billing.preview_order_amount(
                user_id=sub.user_id,
                plan_id=sub.plan_id,
                period_months=sub.period_months,
            )
            user = await billing.user_repo.get_by_id(sub.user_id)
            if user is None or user.balance < preview.amount_due:
                return False
            await billing.create_order(
                OrderCreateIn(
                    user_id=sub.user_id,
                    plan_id=sub.plan_id,
                    provider=PaymentProviderEnum.BALANCE,
                    order_type=OrderTypeEnum.PLAN_PURCHASE,
                    period_months=sub.period_months,
                    subscription_id=sub.id,
                )
            )
            logger.info(
                "auto_renew_charged",
                subscription_id=str(sub.id),
                user_id=str(sub.user_id),
                amount=str(preview.amount_due),
            )
            return True
        except InsufficientBalance:
            return False
        except Exception:
            logger.exception("auto_renew_failed", subscription_id=str(sub.id))
            return False
