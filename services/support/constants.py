SUPPORT_INBOUND_SUBJECT = "support.message.in"
SUPPORT_OUTBOUND_SUBJECT = "support.message.out"
SUPPORT_SENT_SUBJECT = "support.message.sent"
SUPPORT_TICKET_EVENT_SUBJECT = "support.ticket.event"

REOPEN_WINDOW_MIN = 60

SUBJECT_PREVIEW_LEN = 80

MAX_BROADCAST_DISPATCH_ATTEMPTS = 5
BROADCAST_RETRY_BACKOFF_SEC = 120
BROADCAST_SENDING_STALE_SEC = 300

BROADCAST_BUTTON_STYLES = ("primary", "success", "danger")
BROADCAST_BUTTON_ACTIONS = ("renew", "plans", "connect", "help")

DRIP_RECONCILER_INTERVAL_SEC = 60
DRIP_DUE_BATCH_SIZE = 200
DRIP_ENROLLMENT_DURABLE = "vpn-control-api-drip-enrollment"

DRIP_TRIGGER_EVENTS = (
    "trial_started",
    "purchase",
    "user_registered",
    "subscription_expired",
)
DRIP_CONDITIONS = ("always", "not_connected", "not_purchased", "no_active_sub")


class DripCondition:
    ALWAYS = "always"
    NOT_CONNECTED = "not_connected"
    NOT_PURCHASED = "not_purchased"
    NO_ACTIVE_SUB = "no_active_sub"


class DripStatus:
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    STOPPED = "stopped"
