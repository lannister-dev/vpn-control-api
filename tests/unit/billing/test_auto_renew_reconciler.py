from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from services.billing.exceptions import InsufficientBalance
from services.billing.reconcilers.auto_renew import AutoRenewReconciler


def _rec():
    lock = MagicMock()
    lock.hold = MagicMock()
    return AutoRenewReconciler(tick_lock=lock)


def _billing(balance, *, raises=None):
    b = MagicMock()
    b.preview_order_amount = AsyncMock(
        return_value=SimpleNamespace(amount_due=Decimal("199"))
    )
    b.user_repo = MagicMock()
    b.user_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(balance=balance))
    b.create_order = AsyncMock(side_effect=raises)
    return b


def _sub():
    return SimpleNamespace(id=uuid4(), user_id=uuid4(), plan_id=uuid4(), period_months=1)


async def test_renew_charges_when_balance_enough():
    rec = _rec()
    billing = _billing(Decimal("500"))
    ok = await rec._renew_one(billing, _sub())
    assert ok is True
    billing.create_order.assert_awaited_once()


async def test_renew_skips_when_balance_low():
    rec = _rec()
    billing = _billing(Decimal("50"))
    ok = await rec._renew_one(billing, _sub())
    assert ok is False
    billing.create_order.assert_not_awaited()


async def test_renew_skips_on_insufficient_balance_error():
    rec = _rec()
    billing = _billing(Decimal("500"), raises=InsufficientBalance())
    ok = await rec._renew_one(billing, _sub())
    assert ok is False
