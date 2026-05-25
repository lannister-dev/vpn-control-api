from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import datetime, timezone

from services.config import get_settings
from services.notifications.constants import (
    NOTIFICATIONS_DUPLICATE_WINDOW_S,
    NOTIFICATIONS_MAX_AGE_S,
    NOTIFICATIONS_MAX_MSGS_PER_SUBJECT,
    PROVIDER_FAILURE_ALERT_COOLDOWN_S,
    PROVIDER_FAILURE_THRESHOLD,
    PROVIDER_FAILURE_WINDOW_S,
)
from services.notifications.failure_monitor import ProviderFailureMonitor
from services.notifications.schemas import (
    BackendAllRoutesDownEvent,
    BalanceTopupEvent,
    DigestDailyEvent,
    DigestWeeklyEvent,
    NodeDownEvent,
    NodeRecoveredEvent,
    NotificationEvent,
    PaymentProviderDownEvent,
    PlacementFailedEvent,
    PurchaseEvent,
    RouteBlockedEvent,
    RouteRecoveredEvent,
    TrialStartedEvent,
    UserRegisteredEvent,
)
from shared.nats.client import NatsClient
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("notifications"))

class NotificationService:
    def __init__(self, nats: NatsClient | None):
        self._nats = nats
        self._stream_ensured = False
        nats_cfg = get_settings().nats
        self._stream_name = nats_cfg.js_notifications_stream
        self._subject = nats_cfg.notifications_subject
        self._provider_failures = ProviderFailureMonitor(
            window_seconds=PROVIDER_FAILURE_WINDOW_S,
            threshold=PROVIDER_FAILURE_THRESHOLD,
            alert_cooldown_seconds=PROVIDER_FAILURE_ALERT_COOLDOWN_S,
        )

    async def ensure_stream(self) -> None:
        if self._stream_ensured or self._nats is None or not self._nats.is_connected:
            return
        await self._nats.ensure_stream(
            name=self._stream_name,
            subjects=[self._subject],
            max_msgs_per_subject=NOTIFICATIONS_MAX_MSGS_PER_SUBJECT,
            max_age=NOTIFICATIONS_MAX_AGE_S,
            duplicate_window=NOTIFICATIONS_DUPLICATE_WINDOW_S,
        )
        self._stream_ensured = True

    async def publish(self, event: NotificationEvent) -> None:
        if self._nats is None or not self._nats.is_connected:
            return
        with contextlib.suppress(Exception):
            await self.ensure_stream()
        payload = event.model_dump(mode="json")
        msg_id = f"{event.kind}:{event.event_id}"
        try:
            await self._nats.publish_jetstream(
                subject=self._subject,
                payload=payload,
                msg_id=msg_id,
            )
        except Exception:
            logger.exception("notification_publish_failed", kind=event.kind, event_id=event.event_id)

    async def publish_node_down(
        self,
        *,
        node_id: str,
        node_name: str | None,
        last_seen_at: datetime,
        affected_placements: int = 0,
    ) -> None:
        await self.publish(NodeDownEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            node_id=node_id,
            node_name=node_name,
            last_seen_at=last_seen_at,
            affected_placements=affected_placements,
        ))

    async def publish_node_recovered(
        self,
        *,
        node_id: str,
        node_name: str | None,
        downtime_seconds: int,
    ) -> None:
        await self.publish(NodeRecoveredEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            node_id=node_id,
            node_name=node_name,
            downtime_seconds=downtime_seconds,
        ))

    async def publish_route_blocked(
        self,
        *,
        route_id: str,
        route_name: str,
        node_id: str,
        reason: str,
    ) -> None:
        await self.publish(RouteBlockedEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            route_id=route_id,
            route_name=route_name,
            node_id=node_id,
            reason=reason,
        ))

    async def publish_route_recovered(
        self,
        *,
        route_id: str,
        route_name: str,
    ) -> None:
        await self.publish(RouteRecoveredEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            route_id=route_id,
            route_name=route_name,
        ))

    async def publish_backend_all_routes_down(
        self,
        *,
        backend_node_id: str,
        backend_name: str | None,
        routes_total: int,
    ) -> None:
        await self.publish(BackendAllRoutesDownEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            backend_node_id=backend_node_id,
            backend_name=backend_name,
            routes_total=routes_total,
        ))

    async def publish_placement_failed(
        self,
        *,
        placement_id: str,
        node_id: str,
        error: str,
    ) -> None:
        await self.publish(PlacementFailedEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            placement_id=placement_id,
            node_id=node_id,
            error=error,
        ))

    async def publish_payment_provider_down(
        self,
        *,
        provider: str,
        fail_count: int,
        window_minutes: int,
    ) -> None:
        await self.publish(PaymentProviderDownEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            provider=provider,
            fail_count=fail_count,
            window_minutes=window_minutes,
        ))

    async def record_payment_failure(self, provider: str) -> None:
        should_alert, count = self._provider_failures.record(provider)
        if not should_alert:
            return
        await self.publish_payment_provider_down(
            provider=provider,
            fail_count=count,
            window_minutes=PROVIDER_FAILURE_WINDOW_S // 60,
        )

    def reset_payment_failures(self, provider: str) -> None:
        self._provider_failures.reset(provider)

    async def publish_user_registered(
        self,
        *,
        telegram_id: int,
        username: str | None = None,
        referral_code: str | None = None,
        source: str | None = None,
    ) -> None:
        await self.publish(UserRegisteredEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            telegram_id=telegram_id,
            username=username,
            referral_code=referral_code,
            source=source,
        ))

    async def publish_trial_started(
        self,
        *,
        telegram_id: int,
        username: str | None,
        plan_name: str,
        days: int,
    ) -> None:
        await self.publish(TrialStartedEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            telegram_id=telegram_id,
            username=username,
            plan_name=plan_name,
            days=days,
        ))

    async def publish_purchase(
        self,
        *,
        telegram_id: int,
        username: str | None,
        plan_name: str,
        amount_rub: float,
        provider: str,
        is_renewal: bool = False,
    ) -> None:
        await self.publish(PurchaseEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            telegram_id=telegram_id,
            username=username,
            plan_name=plan_name,
            amount_rub=amount_rub,
            provider=provider,
            is_renewal=is_renewal,
        ))

    async def publish_balance_topup(
        self,
        *,
        telegram_id: int,
        username: str | None,
        amount_rub: float,
        provider: str,
        balance_after_rub: float,
    ) -> None:
        await self.publish(BalanceTopupEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            telegram_id=telegram_id,
            username=username,
            amount_rub=amount_rub,
            provider=provider,
            balance_after_rub=balance_after_rub,
        ))

    async def publish_digest_daily(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
        registrations: int,
        trials: int,
        purchases: int,
        purchases_rub: float,
        active_subscriptions: int,
        trial_to_paid_pct: float | None = None,
    ) -> None:
        await self.publish(DigestDailyEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            period_start=period_start,
            period_end=period_end,
            registrations=registrations,
            trials=trials,
            purchases=purchases,
            purchases_rub=purchases_rub,
            active_subscriptions=active_subscriptions,
            trial_to_paid_pct=trial_to_paid_pct,
        ))

    async def publish_digest_weekly(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
        registrations: int,
        trials: int,
        purchases: int,
        purchases_rub: float,
        active_subscriptions: int,
        trial_to_paid_pct: float | None = None,
    ) -> None:
        await self.publish(DigestWeeklyEvent(
            event_id=_new_id(),
            emitted_at=_now(),
            period_start=period_start,
            period_end=period_end,
            registrations=registrations,
            trials=trials,
            purchases=purchases,
            purchases_rub=purchases_rub,
            active_subscriptions=active_subscriptions,
            trial_to_paid_pct=trial_to_paid_pct,
        ))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())
