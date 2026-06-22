DRIP_RECONCILER_INTERVAL_SEC = 60
DRIP_DUE_BATCH_SIZE = 200
DRIP_ENROLLMENT_DURABLE = "vpn-control-api-drip-enrollment"

TRIGGER_EVENTS = ("trial_started", "purchase", "user_registered")


class DripCondition:
    ALWAYS = "always"
    NOT_CONNECTED = "not_connected"
    NOT_PURCHASED = "not_purchased"


class DripStatus:
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    STOPPED = "stopped"
