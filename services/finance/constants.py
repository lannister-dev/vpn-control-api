DEFAULT_CURRENCY = "RUB"

EXPENSE_KINDS = (
    "infrastructure",
    "gateway_fee",
    "domain_cdn",
    "marketing",
    "salary",
    "referral",
    "tax",
    "other",
)

RECURRING_PERIODS = ("weekly", "monthly", "yearly")

MATERIALIZE_CATCHUP_LIMIT = 60

MATERIALIZE_TICK_SEC = 3600
