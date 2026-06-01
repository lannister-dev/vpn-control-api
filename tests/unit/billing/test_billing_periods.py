from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from services.billing.schemas import OrderCreateIn, PaymentProviderEnum
from services.billing.service import BillingService


def _period(months: int, price_rub, price_stars=None):
    return SimpleNamespace(
        months=months, price_rub=Decimal(str(price_rub)), price_stars=price_stars
    )


def _plan(price_rub="300", periods=None, price_stars=None):
    return SimpleNamespace(
        id=uuid4(),
        price_rub=Decimal(str(price_rub)),
        price_stars=price_stars,
        periods=periods or [],
    )


class TestResolvePeriodPrice:
    def test_month_uses_period_row(self):
        plan = _plan(price_rub="300", periods=[_period(1, "299")])
        assert BillingService._resolve_period_price(plan, 1) == Decimal("299")

    def test_month_falls_back_to_plan_price(self):
        plan = _plan(price_rub="300", periods=[])
        assert BillingService._resolve_period_price(plan, 1) == Decimal("300")

    def test_year_from_period(self):
        plan = _plan(periods=[_period(1, "300"), _period(12, "3000")])
        assert BillingService._resolve_period_price(plan, 12) == Decimal("3000")

    def test_missing_period_returns_none(self):
        plan = _plan(periods=[_period(1, "300")])
        assert BillingService._resolve_period_price(plan, 6) is None

    def test_stars_resolution(self):
        plan = _plan(periods=[_period(12, "3000", price_stars=1500)])
        assert BillingService._resolve_period_price_stars(plan, 12) == 1500


class TestProration:
    def test_no_remaining_time(self):
        now = datetime.now(timezone.utc)
        plan = _plan(periods=[_period(1, "300")])
        assert BillingService._proration_value(plan, 1, now - timedelta(days=1), now) == Decimal("0")

    def test_half_month_remaining(self):
        now = datetime.now(timezone.utc)
        plan = _plan(price_rub="300", periods=[_period(1, "300")])
        value = BillingService._proration_value(plan, 1, now + timedelta(days=15), now)
        assert value == Decimal("150.00")

    def test_year_remaining(self):
        now = datetime.now(timezone.utc)
        plan = _plan(periods=[_period(1, "300"), _period(12, "3000")])
        value = BillingService._proration_value(plan, 12, now + timedelta(days=182), now)
        expected = (Decimal("3000") * Decimal(182) / Decimal(365)).quantize(Decimal("0.01"))
        assert value == expected

    def test_unknown_old_price_zero(self):
        now = datetime.now(timezone.utc)
        plan = _plan(price_rub="0", periods=[])
        assert BillingService._proration_value(plan, 1, now + timedelta(days=10), now) == Decimal("0")


class TestOrderPreview:
    def _service(self):
        svc = BillingService.__new__(BillingService)
        svc.plan_repo = AsyncMock()
        svc.sub_repo = AsyncMock()
        svc.sub_repo.list_by_user_id = AsyncMock(return_value=[])
        return svc

    async def test_preview_no_switch(self):
        svc = self._service()
        plan = _plan(periods=[_period(1, "299"), _period(12, "2890")])
        svc.plan_repo.get_by_id = AsyncMock(return_value=plan)
        out = await svc.preview_order_amount(user_id=uuid4(), plan_id=plan.id, period_months=12)
        assert out.period_price == Decimal("2890")
        assert out.proration_credit == Decimal("0")
        assert out.amount_due == Decimal("2890")
        assert out.is_switch is False

    async def test_preview_switch_applies_credit(self):
        svc = self._service()
        now = datetime.now(timezone.utc)
        old_plan = _plan(price_rub="199", periods=[_period(1, "199")])
        new_plan = _plan(price_rub="349", periods=[_period(1, "349")])
        current = SimpleNamespace(
            plan_id=old_plan.id, period_months=1,
            expires_at=now + timedelta(days=20), is_active=True,
        )
        svc.sub_repo.list_by_user_id = AsyncMock(return_value=[current])

        async def _get(pid):
            return old_plan if pid == old_plan.id else new_plan
        svc.plan_repo.get_by_id = AsyncMock(side_effect=_get)

        out = await svc.preview_order_amount(user_id=uuid4(), plan_id=new_plan.id, period_months=1)
        assert out.is_switch is True
        assert out.proration_credit > Decimal("0")
        assert out.amount_due == out.period_price - out.proration_credit


class TestOrderPeriodValidation:
    def test_valid_period(self):
        order = OrderCreateIn(
            user_id=uuid4(), plan_id=uuid4(),
            provider=PaymentProviderEnum.CRYPTO, period_months=12,
        )
        assert order.period_months == 12

    def test_invalid_period_rejected(self):
        with pytest.raises(ValidationError):
            OrderCreateIn(
                user_id=uuid4(), plan_id=uuid4(),
                provider=PaymentProviderEnum.CRYPTO, period_months=5,
            )
