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

ACQUISITION_EXPENSE_KINDS = ("marketing", "referral")

METRICS_WINDOW_DAYS = 30

MONTH_LABELS_RU = (
    "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
)
