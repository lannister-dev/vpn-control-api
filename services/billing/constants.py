ORDER_FINAL_STATUSES = ("paid", "completed", "refunded", "failed")
ORDER_REFUNDABLE_STATUSES = ("paid", "completed")

DEFAULT_PERIOD_MONTHS = 1
ALLOWED_PERIOD_MONTHS = (1, 3, 6, 12)
PERIOD_DAYS: dict[int, int] = {1: 30, 3: 90, 6: 180, 12: 365}
