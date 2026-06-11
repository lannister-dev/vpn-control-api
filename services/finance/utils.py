from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal


def add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def advance_period(dt: datetime, period: str) -> datetime:
    if period == "weekly":
        return dt + timedelta(weeks=1)
    if period == "yearly":
        return add_months(dt, 12)
    return add_months(dt, 1)


def normalize_to_rub(
    amount: Decimal, currency: str, fx_rate: Decimal | None
) -> Decimal:
    if currency.upper() == "RUB":
        return amount
    if fx_rate is None or fx_rate <= 0:
        raise ValueError("fx_rate is required and must be > 0 for non-RUB currency")
    return (amount * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def default_range(
    date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime, datetime]:
    end = date_to or datetime.now(timezone.utc)
    start = date_from or (end - timedelta(days=30))
    return start, end
