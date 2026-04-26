from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.billing.reconciler import BillingOrderExpirationReconciler
from services.config import BillingConfig


@pytest.fixture
def cfg():
    return BillingConfig(
        expiration_reconciler_enabled=True,
        expiration_tick_sec=60,
        expiration_batch_size=100,
    )


def _make_reconciler(cfg):
    lock = MagicMock()
    lock.hold = MagicMock()
    return BillingOrderExpirationReconciler(billing_settings=cfg, tick_lock=lock)


async def test_disabled_run_once_returns_none():
    cfg = BillingConfig(expiration_reconciler_enabled=False)
    rec = _make_reconciler(cfg)
    assert await rec.run_once() is None


async def test_run_once_skips_when_lock_not_acquired(cfg):
    rec = _make_reconciler(cfg)

    class _Cm:
        async def __aenter__(self):
            return False

        async def __aexit__(self, exc_type, exc, tb):
            return False

    rec._tick_lock.hold = MagicMock(return_value=_Cm())
    assert await rec.run_once() is None


async def test_execute_tick_expires_pending_orders(cfg):
    rec = _make_reconciler(cfg)

    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False

    rec._session_maker = MagicMock(return_value=fake_session)

    with patch(
        "services.billing.reconciler.OrderRepository"
    ) as RepoCls:
        repo = RepoCls.return_value
        repo.bulk_expire_pending = AsyncMock(return_value=3)
        count = await rec._execute_tick()

    assert count == 3
    fake_session.commit.assert_awaited_once()


async def test_execute_tick_no_orders_no_commit(cfg):
    rec = _make_reconciler(cfg)

    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False

    rec._session_maker = MagicMock(return_value=fake_session)

    with patch(
        "services.billing.reconciler.OrderRepository"
    ) as RepoCls:
        repo = RepoCls.return_value
        repo.bulk_expire_pending = AsyncMock(return_value=0)
        count = await rec._execute_tick()

    assert count == 0
    fake_session.commit.assert_not_awaited()
