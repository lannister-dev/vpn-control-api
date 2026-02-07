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

NODE_ASSIGNMENT_REPORT_TOTAL = Counter(
    "node_assignment_report_total",
    "Assignment reconciliation reports",
    ["status"],
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

# ── Redis Cache (assignments) ──────────────────────────────────
ASSIGNMENT_CACHE_HIT_TOTAL = Counter(
    "assignment_cache_hit_total",
    "Assignment cache hits",
)

ASSIGNMENT_CACHE_MISS_TOTAL = Counter(
    "assignment_cache_miss_total",
    "Assignment cache misses",
)
