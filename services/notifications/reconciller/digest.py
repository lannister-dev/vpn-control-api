from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from services.billing.models import PaymentOrder
from services.notifications.service import NotificationService
from services.users.models import User
from services.vpn.subscriptions.models import Subscription
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.client import redis_client
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("notifications-digest-reconciler"))

DAILY_TRIGGER_HOUR_UTC = 6
WEEKLY_TRIGGER_HOUR_UTC = 7
WEEKLY_TRIGGER_WEEKDAY = 0

REDIS_KEY_DAILY = "notifications:digest:daily:emitted"
REDIS_KEY_WEEKLY = "notifications:digest:weekly:emitted"
REDIS_STATE_TTL_SEC = 60 * 60 * 24 * 8


class NotificationsDigestReconciler(Reconciler):
    name = "notifications_digest"

    def __init__(
        self,
        *,
        notifications: NotificationService,
        interval_sec: int = 60,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(interval_sec=max(30, int(interval_sec)), tick_lock=tick_lock)
        self._notifications = notifications
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> None:
        await self._maybe_emit_daily()
        await self._maybe_emit_weekly()

    async def _maybe_emit_daily(self) -> None:
        now = datetime.now(timezone.utc)
        if now.hour < DAILY_TRIGGER_HOUR_UTC:
            return
        marker = now.strftime("%Y-%m-%d")
        if await self._already_emitted(REDIS_KEY_DAILY, marker):
            return
        period_end = now
        period_start = now - timedelta(days=1)
        stats = await self._collect_stats(period_start=period_start, period_end=period_end)
        await self._notifications.publish_digest_daily(
            period_start=period_start,
            period_end=period_end,
            registrations=stats["registrations"],
            trials=stats["trials"],
            purchases=stats["purchases"],
            purchases_rub=stats["purchases_rub"],
            active_subscriptions=stats["active_subscriptions"],
            trial_to_paid_pct=stats["trial_to_paid_pct"],
        )
        await self._mark_emitted(REDIS_KEY_DAILY, marker)
        logger.info("digest_daily_emitted", marker=marker)

    async def _maybe_emit_weekly(self) -> None:
        now = datetime.now(timezone.utc)
        if now.weekday() != WEEKLY_TRIGGER_WEEKDAY:
            return
        if now.hour < WEEKLY_TRIGGER_HOUR_UTC:
            return
        iso_year, iso_week, _ = now.isocalendar()
        marker = f"{iso_year}-W{iso_week:02d}"
        if await self._already_emitted(REDIS_KEY_WEEKLY, marker):
            return
        period_end = now
        period_start = now - timedelta(days=7)
        stats = await self._collect_stats(period_start=period_start, period_end=period_end)
        await self._notifications.publish_digest_weekly(
            period_start=period_start,
            period_end=period_end,
            registrations=stats["registrations"],
            trials=stats["trials"],
            purchases=stats["purchases"],
            purchases_rub=stats["purchases_rub"],
            active_subscriptions=stats["active_subscriptions"],
            trial_to_paid_pct=stats["trial_to_paid_pct"],
        )
        await self._mark_emitted(REDIS_KEY_WEEKLY, marker)
        logger.info("digest_weekly_emitted", marker=marker)

    async def _collect_stats(self, *, period_start: datetime, period_end: datetime) -> dict:
        async with self._session_maker() as session:
            registrations = await session.scalar(
                select(func.count(User.id)).where(
                    User.created_at >= period_start,
                    User.created_at < period_end,
                )
            ) or 0

            paid_in_window = await session.execute(
                select(func.count(PaymentOrder.id), func.coalesce(func.sum(PaymentOrder.amount_rub), 0)).where(
                    PaymentOrder.status.in_(("paid", "completed")),
                    PaymentOrder.paid_at >= period_start,
                    PaymentOrder.paid_at < period_end,
                    PaymentOrder.order_type.in_(("plan_purchase", "subscription_renewal")),
                    PaymentOrder.provider != "free",
                )
            )
            purchases, purchases_rub_raw = paid_in_window.one()
            purchases_rub = float(purchases_rub_raw or Decimal("0"))

            trials = await session.scalar(
                select(func.count(PaymentOrder.id)).where(
                    PaymentOrder.status.in_(("paid", "completed")),
                    PaymentOrder.paid_at >= period_start,
                    PaymentOrder.paid_at < period_end,
                    PaymentOrder.order_type == "plan_purchase",
                    PaymentOrder.provider == "free",
                )
            ) or 0

            active_subscriptions = await session.scalar(
                select(func.count(Subscription.id)).where(
                    Subscription.expires_at > period_end,
                )
            ) or 0

            trial_to_paid_pct: float | None = None
            if trials > 0:
                trial_to_paid_pct = (int(purchases) / (int(purchases) + int(trials))) * 100.0

            return {
                "registrations": int(registrations),
                "trials": int(trials),
                "purchases": int(purchases),
                "purchases_rub": purchases_rub,
                "active_subscriptions": int(active_subscriptions),
                "trial_to_paid_pct": trial_to_paid_pct,
            }

    async def _already_emitted(self, key: str, marker: str) -> bool:
        try:
            value = await redis_client.client.get(key)
        except Exception:
            return False
        return value == marker

    async def _mark_emitted(self, key: str, marker: str) -> None:
        try:
            await redis_client.client.set(key, marker, ex=REDIS_STATE_TTL_SEC)
        except Exception:
            logger.exception("digest_emit_marker_save_failed", key=key)
