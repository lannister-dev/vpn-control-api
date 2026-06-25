SCENARIO_RECONCILER_INTERVAL_SEC = 60
SCENARIO_DUE_BATCH_SIZE = 200
SCENARIO_ENROLLMENT_DURABLE = "vpn-control-api-scenario-enrollment"

SCENARIO_BUTTON_STYLES = ("primary", "success", "danger")
SCENARIO_BUTTON_ACTIONS = ("renew", "plans", "connect", "help")

SCENARIO_TRIGGERS = (
    "trial_started",
    "purchase",
    "user_registered",
    "subscription_expired",
)
SCENARIO_CONDITIONS = (
    "always",
    "not_connected",
    "not_purchased",
    "no_active_sub",
    "connected",
    "purchased",
)


class ScenarioCondition:
    ALWAYS = "always"
    NOT_CONNECTED = "not_connected"
    NOT_PURCHASED = "not_purchased"
    NO_ACTIVE_SUB = "no_active_sub"
    CONNECTED = "connected"
    PURCHASED = "purchased"


class ScenarioStatus:
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    STOPPED = "stopped"
