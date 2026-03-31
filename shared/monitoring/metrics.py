from prometheus_client import Counter, Histogram, Gauge

# ── Subscriptions ──────────────────────────────────────────────
SUBSCRIPTION_REQUEST_TOTAL = Counter(
    "subscription_request_total",
    "Total subscription config requests by result",
    ["result"],
)

SUBSCRIPTION_BUILD_DURATION = Histogram(
    "subscription_build_duration_seconds",
    "Time to build subscription payload",
)

SUBSCRIPTION_CACHE_TOTAL = Counter(
    "subscription_cache_total",
    "Subscription response cache operations by result",
    ["result"],
)

SUBSCRIPTION_PAYLOAD_SIZE_BYTES = Histogram(
    "subscription_payload_size_bytes",
    "Built subscription payload size in bytes",
)

SUBSCRIPTION_PAYLOAD_GUARDRAIL_TOTAL = Counter(
    "subscription_payload_guardrail_total",
    "Subscription payload guardrail outcomes",
    ["result"],
)

# ── Node Agent ─────────────────────────────────────────────────
NODE_BOOTSTRAP_TOTAL = Counter(
    "node_bootstrap_total",
    "Node bootstrap events",
    ["result"],
)

NODE_HEARTBEAT_TOTAL = Counter(
    "node_heartbeat_total",
    "Node heartbeat events",
)

NODE_SYNC_REPORT_TOTAL = Counter(
    "node_sync_report_total",
    "Node sync report events",
    ["status"],
)

NODE_PLACEMENT_REPORT_TOTAL = Counter(
    "node_placement_report_total",
    "Placement reconciliation reports",
    ["status"],
)

NODE_STATE_FRESHNESS_SECONDS = Gauge(
    "node_state_freshness_seconds",
    "Seconds since last heartbeat for active node (-1 if missing)",
    ["node_id"],
)

PLACEMENT_ORPHAN_ACTIVE_TOTAL = Gauge(
    "placement_orphan_active_total",
    "Active placements currently bound to unavailable backends",
)

PLACEMENT_ACTIVE_BY_BACKEND = Gauge(
    "placement_active_by_backend",
    "Desired active placements by backend node",
    ["node_id"],
)

PLACEMENT_AUTO_HEAL_TOTAL = Counter(
    "placement_auto_heal_total",
    "Placement auto-heal actions",
    ["action", "result"],
)

CONNECT_TELEMETRY_TOTAL = Counter(
    "connect_telemetry_total",
    "Client connect telemetry events processed",
    ["event", "status", "action"],
)

# ── Probe ───────────────────────────────────────────
PROBE_REPORT_TOTAL = Counter(
    "probe_report_total",
    "Probe report ingestion results",
    ["status"],
)

PROBE_ACTION_TOTAL = Counter(
    "probe_action_total",
    "Probe-triggered admin actions",
    ["action", "result"],
)

# ── VPN Keys ───────────────────────────────────────────────────
VPN_KEY_OPERATION_TOTAL = Counter(
    "vpn_key_operation_total",
    "VPN key lifecycle operations",
    ["operation"],
)

# ── Auth ───────────────────────────────────────────────────────
AUTH_ATTEMPT_TOTAL = Counter(
    "auth_attempt_total",
    "Authentication attempts",
    ["type", "result"],
)

# ── Artifacts & Profile Registry ───────────────────────────────
PROFILE_ARTIFACT_VERSION = Gauge(
    "profile_artifact_version",
    "Currently active profile artifact version",
)

PROFILE_REGISTRY_RELOAD_TOTAL = Counter(
    "profile_registry_reload_total",
    "Profile registry reload attempts",
    ["result"],
)

# ── Billing ───────────────────────────────────────────────────
BILLING_ORDER_TOTAL = Counter(
    "billing_order_total",
    "Billing order lifecycle events",
    ["provider", "status"],
)

BILLING_PAYMENT_AMOUNT_RUB_TOTAL = Counter(
    "billing_payment_amount_rub_total",
    "Total payment amount received in RUB",
    ["provider"],
)

BILLING_BALANCE_OPERATION_TOTAL = Counter(
    "billing_balance_operation_total",
    "Balance operations by type",
    ["type"],
)
