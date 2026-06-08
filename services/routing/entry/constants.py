KV_BUCKET = "entry-routing"
KV_STATS_BUCKET = "entry-routing-stats"
KV_KEY_PREFIX = "node."

# An entry node is only eligible for issuance if its agent heartbeat is fresher
# than this. Entry is baked into the issued config and cannot fail over, so a
# node whose is_healthy flag lags behind a dead heartbeat must not be selected.
ENTRY_HEARTBEAT_STALE_SEC = 90

PUBLISHER_TICK_SEC_DEFAULT = 30
PUBLISHER_IDLE_WHEN_DISABLED_SEC = 60
