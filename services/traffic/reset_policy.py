"""Traffic reset policy: cutoff calculation and resettable strategies.

Pure functions — no IO, no DB, easily testable.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from services.plans.schemas import ResetStrategy

RESETTABLE_STRATEGIES: tuple[ResetStrategy, ...] = (
    ResetStrategy.DAY,
    ResetStrategy.WEEK,
    ResetStrategy.MONTH,
)


def reset_cutoff(strategy: ResetStrategy, now: datetime) -> datetime:
    """Return the cutoff timestamp for a given strategy.

    Subscriptions whose ``last_traffic_reset_at`` is before this cutoff
    are eligible for a traffic reset.
    """
    if strategy is ResetStrategy.DAY:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if strategy is ResetStrategy.WEEK:
        monday = now - timedelta(days=now.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    if strategy is ResetStrategy.MONTH:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Non-resettable strategy: {strategy}")
