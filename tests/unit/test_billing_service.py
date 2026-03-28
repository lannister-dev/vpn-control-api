from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.billing.exceptions import (
    DeviceSlotLimitExceeded,
    OrderExpired,
    OrderNotFound,
    PlanNotPurchasable,
    ProviderError,
    WebhookVerificationFailed,
)
from services.billing.schemas import BalanceCreditIn, OrderCreateIn, OrderTypeEnum, PaymentProviderEnum
from services.billing.service import BillingService


def _make_user(*, balance: Decimal = Decimal("100.00")):
    return SimpleNamespace(
        id=uuid4(),
        telegram_id=123456,
        username="testuser",
        balance=balance,
        tag=None,
        description=None,
    )


def _make_plan(
    *,
    name: str = "Pro",
    price_rub: Decimal = Decimal("299.00"),
    is_active: bool = True,
    included_devices: int = 1,
    device_price_rub: Decimal = Decimal("79.00"),
    max_devices: int = 5,
):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        description=None,
        traffic_limit_bytes=10737418240,
        reset_strategy="MONTH",
        max_devices=max_devices,
        included_devices=included_devices,
        duration_days=30,
        sort_order=0,
        is_active=is_active,
        whitelist_enabled=False,
        price_rub=price_rub,
        device_price_rub=device_price_rub,
        device_price_stars=None,
        price_stars=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_order(
    *,
    user_id=None,
    plan_id=None,
    status: str = "pending",
    amount_rub: Decimal = Decimal("299.00"),
    provider: str = "crypto",
    external_id: str = "crypto_abc123",
    order_type: str = "plan_purchase",
    device_slots_qty: int = 0,
    subscription_id=None,
):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id or uuid4(),
        plan_id=plan_id or uuid4(),
        amount_rub=amount_rub,
        provider=provider,
        status=status,
        external_id=external_id,
        payment_url="https://pay.example.com/abc",
        provider_meta=None,
        paid_at=None,
        completed_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        subscription_id=subscription_id,
        order_type=order_type,
        device_slots_qty=device_slots_qty,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_active=True,
    )


def _make_subscription(*, user_id=None, plan_id=None, expires_at=None, paid_device_slots=0):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id or uuid4(),
        plan_id=plan_id or uuid4(),
        token_hash="a" * 64,
        is_active=True,
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=15)),
        max_devices=5,
        paid_device_slots=paid_device_slots,
    )


@pytest.fixture()
def service(async_session):
    svc = BillingService(async_session)
    svc.order_repo = AsyncMock()
    svc.tx_repo = AsyncMock()
    svc.user_repo = AsyncMock()
    svc.plan_repo = AsyncMock()
    svc.sub_repo = AsyncMock()
    svc.settings = SimpleNamespace(order_ttl_minutes=30)
    return svc


# ── create_order ──────────────────────────────────────────────


class TestCreateOrder:
    async def test_create_order_success(self, service):
        user = _make_user()
        plan = _make_plan()
        service.user_repo.get_by_id.return_value = user
        service.plan_repo.get_by_id.return_value = plan

        order = _make_order(user_id=user.id, plan_id=plan.id)
        service.order_repo.create.return_value = order

        with patch.object(
            BillingService,
            "_get_provider",
            return_value=AsyncMock(
                create_payment=AsyncMock(
                    return_value=SimpleNamespace(
                        external_id="crypto_test",
                        payment_url="https://pay.example.com",
                        provider_meta=None,
                    )
                )
            ),
        ):
            result = await service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    plan_id=plan.id,
                    provider=PaymentProviderEnum.CRYPTO,
                )
            )

        assert result.id == order.id
        service.order_repo.create.assert_awaited_once()

    async def test_create_order_user_not_found(self, service):
        service.user_repo.get_by_id.return_value = None
        with pytest.raises(OrderNotFound):
            await service.create_order(
                OrderCreateIn(
                    user_id=uuid4(),
                    plan_id=uuid4(),
                    provider=PaymentProviderEnum.CRYPTO,
                )
            )

    async def test_create_order_inactive_plan(self, service):
        user = _make_user()
        plan = _make_plan(is_active=False)
        service.user_repo.get_by_id.return_value = user
        service.plan_repo.get_by_id.return_value = plan

        with pytest.raises(PlanNotPurchasable):
            await service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    plan_id=plan.id,
                    provider=PaymentProviderEnum.CRYPTO,
                )
            )

    async def test_create_order_zero_price(self, service):
        user = _make_user()
        plan = _make_plan(price_rub=Decimal("0"))
        service.user_repo.get_by_id.return_value = user
        service.plan_repo.get_by_id.return_value = plan

        with pytest.raises(PlanNotPurchasable):
            await service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    plan_id=plan.id,
                    provider=PaymentProviderEnum.STARS,
                )
            )


# ── process_webhook ───────────────────────────────────────────


class TestProcessWebhook:
    async def test_webhook_happy_path(self, service):
        user = _make_user(balance=Decimal("0"))
        plan = _make_plan(price_rub=Decimal("299.00"))
        order = _make_order(
            user_id=user.id,
            plan_id=plan.id,
            status="pending",
            amount_rub=Decimal("299.00"),
        )

        service.order_repo.get_by_external_id.return_value = order
        service.order_repo.update_by_id.return_value = order
        service.plan_repo.get_by_id.return_value = plan

        # _lock_user: first call returns user with 0, second after credit returns 299
        user_after_credit = _make_user(balance=Decimal("299.00"))
        user_after_credit.id = user.id

        async def mock_lock(uid):
            return user_after_credit

        service._lock_user = AsyncMock(side_effect=mock_lock)
        service._update_user_balance = AsyncMock()
        service._record_transaction = AsyncMock()
        service._auto_purchase = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.verify_webhook.return_value = SimpleNamespace(
            external_id=order.external_id,
            amount_rub=299.0,
            provider_meta=None,
        )

        request = MagicMock()
        with patch.object(BillingService, "_get_provider", return_value=mock_provider):
            await service.process_webhook("crypto", request)

        service._update_user_balance.assert_awaited()
        service._record_transaction.assert_awaited()

    async def test_webhook_idempotency_skip(self, service):
        order = _make_order(status="completed")
        service.order_repo.get_by_external_id.return_value = order

        mock_provider = AsyncMock()
        mock_provider.verify_webhook.return_value = SimpleNamespace(
            external_id=order.external_id,
            amount_rub=299.0,
            provider_meta=None,
        )

        request = MagicMock()
        with patch.object(BillingService, "_get_provider", return_value=mock_provider):
            await service.process_webhook("crypto", request)

        # Should not update anything
        service.order_repo.update_by_id.assert_not_awaited()

    async def test_webhook_expired_order(self, service):
        order = _make_order(status="expired")
        service.order_repo.get_by_external_id.return_value = order

        mock_provider = AsyncMock()
        mock_provider.verify_webhook.return_value = SimpleNamespace(
            external_id=order.external_id,
            amount_rub=299.0,
            provider_meta=None,
        )

        request = MagicMock()
        with patch.object(BillingService, "_get_provider", return_value=mock_provider):
            with pytest.raises(OrderExpired):
                await service.process_webhook("crypto", request)

    async def test_webhook_order_not_found(self, service):
        service.order_repo.get_by_external_id.return_value = None

        mock_provider = AsyncMock()
        mock_provider.verify_webhook.return_value = SimpleNamespace(
            external_id="unknown_id",
            amount_rub=100.0,
            provider_meta=None,
        )

        request = MagicMock()
        with patch.object(BillingService, "_get_provider", return_value=mock_provider):
            with pytest.raises(OrderNotFound):
                await service.process_webhook("crypto", request)


# ── balance operations ────────────────────────────────────────


class TestBalanceOps:
    async def test_get_balance(self, service):
        user = _make_user(balance=Decimal("500.00"))
        service.user_repo.get_by_id.return_value = user
        result = await service.get_balance(user.id)
        assert result.balance == Decimal("500.00")

    async def test_get_balance_user_not_found(self, service):
        service.user_repo.get_by_id.return_value = None
        with pytest.raises(OrderNotFound):
            await service.get_balance(uuid4())

    async def test_credit_balance(self, service):
        user = _make_user(balance=Decimal("100.00"))
        service._lock_user = AsyncMock(return_value=user)
        service._update_user_balance = AsyncMock()
        service._record_transaction = AsyncMock()

        result = await service.credit_balance(
            user.id, BalanceCreditIn(amount=Decimal("50.00"), description="Bonus")
        )
        assert result.balance == Decimal("150.00")
        service._update_user_balance.assert_awaited_once()
        service._record_transaction.assert_awaited_once()


# ── auto_purchase ─────────────────────────────────────────────


class TestAutoPurchase:
    async def test_auto_purchase_new_subscription(self, service, async_session):
        user = _make_user(balance=Decimal("299.00"))
        plan = _make_plan(price_rub=Decimal("299.00"))
        order = _make_order(user_id=user.id, plan_id=plan.id)
        now = datetime.now(timezone.utc)

        service._lock_user = AsyncMock(return_value=user)
        service._update_user_balance = AsyncMock()
        service._record_transaction = AsyncMock()
        service.sub_repo.find_active_subscription = AsyncMock(return_value=None)

        new_sub = _make_subscription(user_id=user.id, plan_id=plan.id)
        service.sub_repo.create.return_value = new_sub
        service.order_repo.update_by_id.return_value = order

        await service._auto_purchase(user, plan, order, now)

        service.sub_repo.create.assert_awaited_once()
        service._update_user_balance.assert_awaited_once()

    async def test_auto_purchase_extend_subscription(self, service, async_session):
        user = _make_user(balance=Decimal("299.00"))
        plan = _make_plan(price_rub=Decimal("299.00"))
        order = _make_order(user_id=user.id, plan_id=plan.id)
        now = datetime.now(timezone.utc)
        existing_sub = _make_subscription(
            user_id=user.id,
            plan_id=plan.id,
            expires_at=now + timedelta(days=15),
        )

        service._lock_user = AsyncMock(return_value=user)
        service._update_user_balance = AsyncMock()
        service._record_transaction = AsyncMock()
        service.sub_repo.find_active_subscription = AsyncMock(return_value=existing_sub)
        service.sub_repo.update_by_id.return_value = existing_sub
        service.order_repo.update_by_id.return_value = order

        await service._auto_purchase(user, plan, order, now)

        # Should extend, not create new
        service.sub_repo.create.assert_not_awaited()
        service.sub_repo.update_by_id.assert_awaited_once()
        call_args = service.sub_repo.update_by_id.call_args
        new_expires = call_args[0][1]["expires_at"]
        assert new_expires > existing_sub.expires_at

    async def test_auto_purchase_insufficient_balance(self, service, async_session):
        user = _make_user(balance=Decimal("10.00"))
        plan = _make_plan(price_rub=Decimal("299.00"))
        order = _make_order(user_id=user.id, plan_id=plan.id)
        now = datetime.now(timezone.utc)

        service._lock_user = AsyncMock(return_value=user)

        await service._auto_purchase(user, plan, order, now)

        # Should not create subscription or update balance
        service.sub_repo.create.assert_not_awaited()


# ── list operations ───────────────────────────────────────────


class TestListOperations:
    async def test_list_user_orders(self, service):
        orders = [_make_order(), _make_order()]
        service.order_repo.list_by_user.return_value = (orders, 2)
        result = await service.list_user_orders(uuid4())
        assert result.total == 2
        assert len(result.items) == 2

    async def test_list_transactions(self, service):
        txs = [
            SimpleNamespace(
                id=uuid4(),
                user_id=uuid4(),
                amount=Decimal("100"),
                balance_after=Decimal("100"),
                type="payment",
                order_id=None,
                description=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_active=True,
            )
        ]
        service.tx_repo.list_by_user.return_value = (txs, 1)
        result = await service.list_transactions(uuid4())
        assert result.total == 1


# ── device slots ─────────────────────────────────────────────


class TestDeviceSlots:
    async def test_create_device_slot_order(self, service):
        user = _make_user()
        plan = _make_plan(max_devices=5, included_devices=1, device_price_rub=Decimal("79.00"))
        sub = _make_subscription(user_id=user.id, plan_id=plan.id, paid_device_slots=0)

        service.user_repo.get_by_id.return_value = user
        service.sub_repo.get_by_id.return_value = sub
        service.plan_repo.get_by_id.return_value = plan

        order = _make_order(
            user_id=user.id,
            order_type="device_slots",
            device_slots_qty=2,
            amount_rub=Decimal("158.00"),
            subscription_id=sub.id,
        )
        service.order_repo.create.return_value = order
        service.order_repo.update_by_id.return_value = order
        service.order_repo.get_by_id.return_value = order

        with patch.object(
            BillingService,
            "_get_provider",
            return_value=AsyncMock(
                create_payment=AsyncMock(
                    return_value=SimpleNamespace(
                        external_id="crypto_test",
                        payment_url="https://pay.example.com",
                        provider_meta=None,
                    )
                )
            ),
        ):
            result = await service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    provider=PaymentProviderEnum.CRYPTO,
                    order_type=OrderTypeEnum.DEVICE_SLOTS,
                    device_slots_qty=2,
                    subscription_id=sub.id,
                )
            )

        assert result.id == order.id
        service.order_repo.create.assert_awaited_once()

    async def test_device_slot_order_exceeds_limit(self, service):
        user = _make_user()
        plan = _make_plan(max_devices=3, included_devices=1, device_price_rub=Decimal("79.00"))
        sub = _make_subscription(user_id=user.id, plan_id=plan.id, paid_device_slots=1)

        service.user_repo.get_by_id.return_value = user
        service.sub_repo.get_by_id.return_value = sub
        service.plan_repo.get_by_id.return_value = plan

        with pytest.raises(DeviceSlotLimitExceeded):
            await service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    provider=PaymentProviderEnum.CRYPTO,
                    order_type=OrderTypeEnum.DEVICE_SLOTS,
                    device_slots_qty=5,
                    subscription_id=sub.id,
                )
            )

    async def test_fulfill_device_slots(self, service, async_session):
        user = _make_user(balance=Decimal("158.00"))
        sub = _make_subscription(user_id=user.id, paid_device_slots=1)
        order = _make_order(
            user_id=user.id,
            order_type="device_slots",
            device_slots_qty=2,
            amount_rub=Decimal("158.00"),
            subscription_id=sub.id,
        )

        service._lock_user = AsyncMock(return_value=user)
        service._update_user_balance = AsyncMock()
        service._record_transaction = AsyncMock()
        service.sub_repo.get_by_id.return_value = sub
        service.sub_repo.update_by_id.return_value = sub

        await service._fulfill_device_slots(user, order, datetime.now(timezone.utc))

        service._update_user_balance.assert_awaited_once()
        service._record_transaction.assert_awaited_once()
        service.sub_repo.update_by_id.assert_awaited_once()
        update_args = service.sub_repo.update_by_id.call_args[0][1]
        assert update_args["paid_device_slots"] == 3  # 1 existing + 2 new

    async def test_auto_purchase_with_extra_devices(self, service, async_session):
        user = _make_user(balance=Decimal("457.00"))
        plan = _make_plan(price_rub=Decimal("299.00"), device_price_rub=Decimal("79.00"))
        order = _make_order(
            user_id=user.id,
            plan_id=plan.id,
            device_slots_qty=2,
            amount_rub=Decimal("457.00"),
        )
        now = datetime.now(timezone.utc)

        service._lock_user = AsyncMock(return_value=user)
        service._update_user_balance = AsyncMock()
        service._record_transaction = AsyncMock()
        service.sub_repo.find_active_subscription = AsyncMock(return_value=None)

        new_sub = _make_subscription(user_id=user.id, plan_id=plan.id)
        service.sub_repo.create.return_value = new_sub
        service.order_repo.update_by_id.return_value = order

        await service._auto_purchase(user, plan, order, now)

        service.sub_repo.create.assert_awaited_once()
        create_args = service.sub_repo.create.call_args[0][0]
        assert create_args["paid_device_slots"] == 2
        assert create_args["max_devices"] == 3  # included(1) + extra(2)
