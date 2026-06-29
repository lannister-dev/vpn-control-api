from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Discriminator, TypeAdapter


class _Base(BaseModel):
    schema_version: int = 1
    event_id: str
    emitted_at: datetime


class NodeDownEvent(_Base):
    kind: Literal["node_down"] = "node_down"
    node_id: str
    node_name: str | None = None
    region: str | None = None
    last_seen_at: datetime
    affected_placements: int = 0


class NodeRecoveredEvent(_Base):
    kind: Literal["node_recovered"] = "node_recovered"
    node_id: str
    node_name: str | None = None
    region: str | None = None
    downtime_seconds: int


class RouteBlockedEvent(_Base):
    kind: Literal["route_blocked"] = "route_blocked"
    route_id: str
    route_name: str
    node_id: str
    reason: str


class RouteRecoveredEvent(_Base):
    kind: Literal["route_recovered"] = "route_recovered"
    route_id: str
    route_name: str


class BackendAllRoutesDownEvent(_Base):
    kind: Literal["backend_all_routes_down"] = "backend_all_routes_down"
    backend_node_id: str
    backend_name: str | None = None
    routes_total: int


class PlacementFailedEvent(_Base):
    kind: Literal["placement_failed"] = "placement_failed"
    placement_id: str
    node_id: str
    error: str


class PaymentProviderDownEvent(_Base):
    kind: Literal["payment_provider_down"] = "payment_provider_down"
    provider: str
    fail_count: int
    window_minutes: int


class UserRegisteredEvent(_Base):
    kind: Literal["user_registered"] = "user_registered"
    telegram_id: int
    username: str | None = None
    referral_code: str | None = None
    source: str | None = None


class TrialStartedEvent(_Base):
    kind: Literal["trial_started"] = "trial_started"
    telegram_id: int
    username: str | None = None
    plan_name: str
    days: int


class PurchaseEvent(_Base):
    kind: Literal["purchase"] = "purchase"
    telegram_id: int
    username: str | None = None
    plan_name: str
    amount_rub: float
    provider: str
    is_renewal: bool = False


class SubscriptionExpiredEvent(_Base):
    kind: Literal["subscription_expired"] = "subscription_expired"
    telegram_id: int
    username: str | None = None
    plan_name: str | None = None


class TrialExpiredEvent(_Base):
    kind: Literal["trial_expired"] = "trial_expired"
    telegram_id: int
    username: str | None = None
    plan_name: str | None = None


class BalanceTopupEvent(_Base):
    kind: Literal["balance_topup"] = "balance_topup"
    telegram_id: int
    username: str | None = None
    amount_rub: float
    provider: str
    balance_after_rub: float


class SupportMessageEvent(_Base):
    kind: Literal["support_message"] = "support_message"
    ticket_id: str
    telegram_id: int
    username: str | None = None
    text: str


class DigestDailyEvent(_Base):
    kind: Literal["digest_daily"] = "digest_daily"
    period_start: datetime
    period_end: datetime
    registrations: int
    trials: int
    purchases: int
    purchases_rub: float
    active_subscriptions: int
    trial_to_paid_pct: float | None = None


class DigestWeeklyEvent(_Base):
    kind: Literal["digest_weekly"] = "digest_weekly"
    period_start: datetime
    period_end: datetime
    registrations: int
    trials: int
    purchases: int
    purchases_rub: float
    active_subscriptions: int
    trial_to_paid_pct: float | None = None


NotificationEvent = Union[
    NodeDownEvent,
    NodeRecoveredEvent,
    RouteBlockedEvent,
    RouteRecoveredEvent,
    BackendAllRoutesDownEvent,
    PlacementFailedEvent,
    PaymentProviderDownEvent,
    UserRegisteredEvent,
    TrialStartedEvent,
    PurchaseEvent,
    BalanceTopupEvent,
    SupportMessageEvent,
    DigestDailyEvent,
    DigestWeeklyEvent,
]

NotificationEventAdapter = TypeAdapter(
    Annotated[NotificationEvent, Discriminator("kind")]
)
