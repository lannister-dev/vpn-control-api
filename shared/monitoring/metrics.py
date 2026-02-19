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

NODE_PLACEMENT_REPORT_TOTAL = Counter(
    "node_placement_report_total",
    "Placement reconciliation reports",
    ["status"],
)

NODE_BACKEND_PEER_REPORT_TOTAL = Counter(
    "node_backend_peer_report_total",
    "Backend peer reconciliation reports",
    ["status"],
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
