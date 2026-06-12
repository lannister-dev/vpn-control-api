from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.promo.exceptions import PromoExhausted, PromoInvalid, PromoNotEligible
from services.promo.service import PromoService


def _promo(**ov):
    base = dict(
        id=uuid4(), code="LETO", is_active=True,
        discount_type="percent", discount_value=Decimal("50"), max_discount_rub=None,
        audience="all", plan_ids=None, applies_to="any",
        min_amount_rub=None, max_activations=None, activation_count=0, max_per_user=1,
        starts_at=None, expires_at=None,
    )
    base.update(ov)
    return SimpleNamespace(**base)


@pytest.fixture()
def svc():
    s = PromoService(AsyncMock())
    s.promo_repo = AsyncMock()
    s.activation_repo = AsyncMock()
    s.sub_repo = AsyncMock()
    s.activation_repo.count_for_user = AsyncMock(return_value=0)
    return s


async def _quote(svc, promo, amount="200", **kw):
    svc.promo_repo.get_by_code = AsyncMock(return_value=promo)
    return await svc.validate_and_quote(
        code="LETO", user_id=uuid4(), plan_id=kw.get("plan_id"),
        order_type=kw.get("order_type", "plan_purchase"), amount_rub=Decimal(amount),
    )


class TestDiscount:
    async def test_percent(self, svc):
        q = await _quote(svc, _promo())
        assert q.discount_rub == Decimal("100.00") and q.amount_after == Decimal("100.00")

    async def test_percent_capped(self, svc):
        q = await _quote(svc, _promo(max_discount_rub=Decimal("30")))
        assert q.discount_rub == Decimal("30")

    async def test_fixed(self, svc):
        q = await _quote(svc, _promo(discount_type="fixed", discount_value=Decimal("50")))
        assert q.discount_rub == Decimal("50") and q.amount_after == Decimal("150")


class TestGuards:
    async def test_expired(self, svc):
        with pytest.raises(PromoInvalid):
            await _quote(svc, _promo(expires_at=datetime.now(timezone.utc) - timedelta(days=1)))

    async def test_min_amount(self, svc):
        with pytest.raises(PromoInvalid):
            await _quote(svc, _promo(min_amount_rub=Decimal("500")), amount="200")

    async def test_total_limit(self, svc):
        with pytest.raises(PromoExhausted):
            await _quote(svc, _promo(max_activations=5, activation_count=5))

    async def test_per_user_limit(self, svc):
        svc.activation_repo.count_for_user = AsyncMock(return_value=1)
        with pytest.raises(PromoExhausted):
            await _quote(svc, _promo(max_per_user=1))

    async def test_by_plan_mismatch(self, svc):
        with pytest.raises(PromoNotEligible):
            await _quote(svc, _promo(audience="by_plan", plan_ids=[str(uuid4())]), plan_id=uuid4())

    async def test_applies_to_renewal(self, svc):
        with pytest.raises(PromoNotEligible):
            await _quote(svc, _promo(applies_to="renewal"), order_type="plan_purchase")

    async def test_no_subscription_ok(self, svc):
        svc.sub_repo.list_by_user_id = AsyncMock(return_value=[])
        q = await _quote(svc, _promo(audience="no_subscription"))
        assert q.amount_after == Decimal("100.00")


class TestCreateAndActivation:
    async def test_create_normalizes_via_schema(self, svc):
        from decimal import Decimal as D

        from services.promo.schemas import (
            DiscountType,
            PromoAudience,
            PromoCodeCreateIn,
        )
        svc.promo_repo.get_by_code = AsyncMock(return_value=None)
        _now = datetime.now(timezone.utc)
        svc.promo_repo.create = AsyncMock(return_value=_promo(
            code="LETO50", description=None, created_at=_now, updated_at=_now,
        ))
        plan = uuid4()
        await svc.create_promo(
            PromoCodeCreateIn(
                code="leto50", discount_type=DiscountType.PERCENT,
                discount_value=D("25"), audience=PromoAudience.BY_PLAN, plan_ids=[plan],
            ),
            actor_admin_id=None,
        )
        payload = svc.promo_repo.create.await_args.args[0]
        assert payload["code"] == "LETO50"          # uppercased
        assert payload["discount_type"] == "percent"  # enum -> value
        assert payload["audience"] == "by_plan"
        assert payload["plan_ids"] == [str(plan)]     # UUID -> str

    async def test_record_activation_payload(self, svc):
        from decimal import Decimal as D
        svc.activation_repo.create = AsyncMock()
        svc.promo_repo.increment_activation = AsyncMock()
        pid, uid, oid = uuid4(), uuid4(), uuid4()
        await svc.record_activation(
            promo_code_id=pid, user_id=uid, order_id=oid,
            amount_before=D("200"), discount_applied=D("50"), amount_after=D("150"),
        )
        p = svc.activation_repo.create.await_args.args[0]
        assert p["promo_code_id"] == pid and p["amount_after"] == D("150")
        svc.promo_repo.increment_activation.assert_awaited_once_with(pid)
