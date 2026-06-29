from enum import Enum

SCENARIO_RECONCILER_INTERVAL_SEC = 60
SCENARIO_DUE_BATCH_SIZE = 200
SCENARIO_ENROLLMENT_DURABLE = "vpn-control-api-scenario-enrollment"
SCENARIO_ENROLL_RETRY_DELAY_SEC = 3

SCENARIO_BUTTON_STYLES = ("primary", "success", "danger")
SCENARIO_BUTTON_ACTIONS = ("renew", "plans", "trial", "connect", "help", "promo")

SCENARIO_TRIGGERS = (
    "trial_started",
    "purchase",
    "user_registered",
    "subscription_expired",
    "trial_expired",
)
class ScenarioCondition(str, Enum):
    ALWAYS = "always"
    NOT_CONNECTED = "not_connected"
    NOT_PURCHASED = "not_purchased"
    NO_ACTIVE_SUB = "no_active_sub"
    CONNECTED = "connected"
    PURCHASED = "purchased"


SCENARIO_CONDITIONS = tuple(c.value for c in ScenarioCondition)


class ScenarioStatus:
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    STOPPED = "stopped"
