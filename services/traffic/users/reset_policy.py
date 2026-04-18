"""Traffic reset policy: cutoff calculation and resettable strategies."""

from __future__ import annotations

from datetime import datetime, timedelta

from services.plans.schemas import ResetStrategy

RESETTABLE_STRATEGIES: tuple[ResetStrategy, ...] = (
    ResetStrategy.DAY,
    ResetStrategy.WEEK,
    ResetStrategy.MONTH,
)


def reset_cutoff(strategy: ResetStrategy, now: datetime) -> datetime:
    if strategy is ResetStrategy.DAY:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if strategy is ResetStrategy.WEEK:
        monday = now - timedelta(days=now.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    if strategy is ResetStrategy.MONTH:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Non-resettable strategy: {strategy}")
