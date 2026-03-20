from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.plans.schemas import (
    PlanCreateIn,
    PlanUpdateIn,
    ResetStrategy,
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
