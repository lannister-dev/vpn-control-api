from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.plans.schemas import ResetStrategy
from services.traffic.reset_policy import (
    RESETTABLE_STRATEGIES,
    reset_cutoff,
)


class TestResettableStrategies:
    def test_contains_day_week_month(self):
        assert ResetStrategy.DAY in RESETTABLE_STRATEGIES
        assert ResetStrategy.WEEK in RESETTABLE_STRATEGIES
        assert ResetStrategy.MONTH in RESETTABLE_STRATEGIES

    def test_does_not_contain_no_reset(self):
        assert ResetStrategy.NO_RESET not in RESETTABLE_STRATEGIES


class TestResetCutoff:
    def test_day_cutoff_is_start_of_day(self):
        now = datetime(2026, 3, 20, 14, 35, 22, tzinfo=timezone.utc)
        cutoff = reset_cutoff(ResetStrategy.DAY, now)
        assert cutoff == datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)

    def test_day_cutoff_at_midnight_returns_same_day(self):
        now = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        cutoff = reset_cutoff(ResetStrategy.DAY, now)
        assert cutoff == now

    def test_week_cutoff_is_monday_of_current_week(self):
        # 2026-03-20 is a Friday
        now = datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc)
        cutoff = reset_cutoff(ResetStrategy.WEEK, now)
        # Monday = 2026-03-16
        assert cutoff == datetime(2026, 3, 16, 0, 0, 0, tzinfo=timezone.utc)

    def test_week_cutoff_on_monday_returns_same_day(self):
        now = datetime(2026, 3, 16, 8, 0, 0, tzinfo=timezone.utc)
        cutoff = reset_cutoff(ResetStrategy.WEEK, now)
        assert cutoff == datetime(2026, 3, 16, 0, 0, 0, tzinfo=timezone.utc)

    def test_month_cutoff_is_first_of_month(self):
        now = datetime(2026, 3, 20, 18, 0, 0, tzinfo=timezone.utc)
        cutoff = reset_cutoff(ResetStrategy.MONTH, now)
        assert cutoff == datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_month_cutoff_on_first_returns_same_day(self):
        now = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        cutoff = reset_cutoff(ResetStrategy.MONTH, now)
        assert cutoff == now

    def test_no_reset_raises(self):
        now = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="Non-resettable"):
            reset_cutoff(ResetStrategy.NO_RESET, now)
