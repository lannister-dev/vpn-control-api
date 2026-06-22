from services.notifications.schemas import (
    BackendAllRoutesDownEvent,
    BalanceTopupEvent,
    DigestDailyEvent,
    DigestWeeklyEvent,
    NodeDownEvent,
    NodeRecoveredEvent,
    PaymentProviderDownEvent,
    PlacementFailedEvent,
    PurchaseEvent,
    RouteBlockedEvent,
    RouteRecoveredEvent,
    SubscriptionExpiredEvent,
    SupportMessageEvent,
    TrialStartedEvent,
    UserRegisteredEvent,
)

EXPECTED_CONTRACT: dict[str, tuple[type, frozenset[str]]] = {
    "node_down": (NodeDownEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "node_id", "node_name", "region", "last_seen_at", "affected_placements",
    })),
    "node_recovered": (NodeRecoveredEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "node_id", "node_name", "region", "downtime_seconds",
    })),
    "route_blocked": (RouteBlockedEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "route_id", "route_name", "node_id", "reason",
    })),
    "route_recovered": (RouteRecoveredEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "route_id", "route_name",
    })),
    "backend_all_routes_down": (BackendAllRoutesDownEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "backend_node_id", "backend_name", "routes_total",
    })),
    "placement_failed": (PlacementFailedEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "placement_id", "node_id", "error",
    })),
    "payment_provider_down": (PaymentProviderDownEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "provider", "fail_count", "window_minutes",
    })),
    "user_registered": (UserRegisteredEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "telegram_id", "username", "referral_code", "source",
    })),
    "support_message": (SupportMessageEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "ticket_id", "telegram_id", "username", "text",
    })),
    "trial_started": (TrialStartedEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "telegram_id", "username", "plan_name", "days",
    })),
    "purchase": (PurchaseEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "telegram_id", "username", "plan_name", "amount_rub", "provider", "is_renewal",
    })),
    "balance_topup": (BalanceTopupEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "telegram_id", "username", "amount_rub", "provider", "balance_after_rub",
    })),
    "subscription_expired": (SubscriptionExpiredEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "telegram_id", "username", "plan_name",
    })),
    "digest_daily": (DigestDailyEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "period_start", "period_end", "registrations", "trials",
        "purchases", "purchases_rub", "active_subscriptions", "trial_to_paid_pct",
    })),
    "digest_weekly": (DigestWeeklyEvent, frozenset({
        "schema_version", "event_id", "emitted_at", "kind",
        "period_start", "period_end", "registrations", "trials",
        "purchases", "purchases_rub", "active_subscriptions", "trial_to_paid_pct",
    })),
}


def test_every_event_kind_has_expected_fields():
    for expected_kind, (cls, expected_fields) in EXPECTED_CONTRACT.items():
        actual_kind = cls.model_fields["kind"].default
        assert actual_kind == expected_kind, f"{cls.__name__} kind drifted: {actual_kind!r} != {expected_kind!r}"
        actual_fields = frozenset(cls.model_fields.keys())
        assert actual_fields == expected_fields, (
            f"{cls.__name__} fields drifted: "
            f"added={actual_fields - expected_fields}, removed={expected_fields - actual_fields}"
        )


def test_no_unknown_event_classes_exist():
    from services.notifications.schemas import _Base
    declared = {cls for cls, _ in EXPECTED_CONTRACT.values()}
    actual = set(_Base.__subclasses__())
    extras = actual - declared
    missing = declared - actual
    assert not extras, f"Unexpected event classes: {[c.__name__ for c in extras]}"
    assert not missing, f"Missing event classes: {[c.__name__ for c in missing]}"
