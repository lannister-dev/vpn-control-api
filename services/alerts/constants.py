DEDUP_WINDOW_SEC: int = 300

LIST_DEFAULT_LIMIT: int = 50
LIST_MAX_LIMIT: int = 200

UNREAD_BADGE_LIMIT: int = 99


class AlertSource:
    PROBE = "probe"
    TRANSPORT = "transport"
    BILLING = "billing"
    DEPLOY = "deploy"
    NATS = "nats"
    SCHEDULER = "scheduler"
    SECURITY = "security"
    GENERIC = "generic"
