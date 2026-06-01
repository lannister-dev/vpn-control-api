from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.plans.schemas import (
    PlanCreateIn,
    PlanPeriodOut,
    PlanUpdateIn,
    ResetStrategy,
    _compute_savings,
)


class TestPlanCreateIn:
    def test_defaults(self):
        p = PlanCreateIn(name="Basic")
        assert p.traffic_limit_bytes == 0
        assert p.reset_strategy == ResetStrategy.NO_RESET
        assert p.max_devices == 5
        assert p.duration_days == 30
        assert p.sort_order == 0

    def test_unlimited_plan(self):
        p = PlanCreateIn(name="Unlimited", traffic_limit_bytes=0)
        assert p.traffic_limit_bytes == 0

    def test_limited_plan(self):
        p = PlanCreateIn(name="10GB", traffic_limit_bytes=10 * 1024 * 1024 * 1024)
        assert p.traffic_limit_bytes == 10737418240

    def test_negative_traffic_rejected(self):
        with pytest.raises(ValidationError):
            PlanCreateIn(name="Bad", traffic_limit_bytes=-1)

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            PlanCreateIn(name="x" * 65)

    def test_max_devices_range(self):
        with pytest.raises(ValidationError):
            PlanCreateIn(name="Bad", max_devices=0)
        with pytest.raises(ValidationError):
            PlanCreateIn(name="Bad", max_devices=101)

    def test_all_reset_strategies_valid(self):
        for strategy in ResetStrategy:
            p = PlanCreateIn(name="Test", reset_strategy=strategy)
            assert p.reset_strategy == strategy


class TestPlanUpdateIn:
    def test_empty_payload_valid(self):
        p = PlanUpdateIn()
        assert p.model_dump(exclude_unset=True) == {}

    def test_partial_update(self):
        p = PlanUpdateIn(traffic_limit_bytes=5368709120, is_active=False)
        data = p.model_dump(exclude_unset=True)
        assert data == {"traffic_limit_bytes": 5368709120, "is_active": False}


class TestPeriodValidation:
    def test_duplicate_months_rejected(self):
        with pytest.raises(ValidationError):
            PlanCreateIn(
                name="Pro",
                periods=[
                    {"months": 1, "price_rub": "299"},
                    {"months": 1, "price_rub": "300"},
                ],
            )

    def test_unique_months_ok(self):
        p = PlanCreateIn(
            name="Pro",
            periods=[
                {"months": 1, "price_rub": "299"},
                {"months": 12, "price_rub": "2890"},
            ],
        )
        assert len(p.periods) == 2


class TestSavingsComputation:
    def _out(self, months, price):
        return PlanPeriodOut(months=months, price_rub=price)

    def test_year_savings(self):
        periods = [self._out(1, "299"), self._out(12, "2890")]
        _compute_savings(periods)
        year = next(p for p in periods if p.months == 12)
        assert year.savings_pct == round((1 - 2890 / (299 * 12)) * 100)

    def test_no_savings_when_not_cheaper(self):
        periods = [self._out(1, "299"), self._out(12, "3588")]
        _compute_savings(periods)
        year = next(p for p in periods if p.months == 12)
        assert year.savings_pct is None

    def test_month_has_no_savings(self):
        periods = [self._out(1, "299")]
        _compute_savings(periods)
        assert periods[0].savings_pct is None

    def test_no_monthly_baseline_noop(self):
        periods = [self._out(6, "990")]
        _compute_savings(periods)
        assert periods[0].savings_pct is None
