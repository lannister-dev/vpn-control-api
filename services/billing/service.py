from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.billing.exceptions import (
    InsufficientBalance,
    OrderAlreadyProcessed,
    OrderExpired,
    OrderNotFound,
    PlanNotPurchasable,
    ProviderError,
    WebhookVerificationFailed,
)
from services.billing.models import BalanceTransaction, PaymentOrder
from services.billing.providers.base import PaymentProvider
from services.billing.providers.crypto import CryptoProvider
from services.billing.providers.platega import PlategaProvider
from services.billing.repository import OrderRepository, TransactionRepository
from services.billing.schemas import (
    BalanceCreditIn,
    BalanceOut,
    OrderCreateIn,
    OrderInternalCreate,
    OrderInternalUpdate,
    OrderListOut,
    OrderOut,
    TransactionInternalCreate,
    TransactionListOut,
    TransactionOut,
)
from services.config import get_settings
from services.plans.repository import PlanRepository
from services.users.models import User
from services.users.repository import UserRepository
from services.vpn.subscriptions.repository import SubscriptionRepository
from services.vpn.subscriptions.schemas import SubscriptionInternalCreate, SubscriptionInternalUpdate
from services.vpn.subscriptions.utils import SubscriptionUtils
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import (
    BILLING_BALANCE_OPERATION_TOTAL,
    BILLING_ORDER_TOTAL,
    BILLING_PAYMENT_AMOUNT_RUB_TOTAL,
)
from shared.utils.logger import StructuredLogger

log = StructuredLogger(logging.getLogger("billing"))

_PROVIDERS: dict[str, type[PaymentProvider]] = {
    "crypto": CryptoProvider,
    "platega": PlategaProvider,
}


class BillingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.order_repo = OrderRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.user_repo = UserRepository(session)
        self.plan_repo = PlanRepository(session)
        self.sub_repo = SubscriptionRepository(session)
        self.settings = get_settings().billing

    # ── Provider factory ──────────────────────────────────────

    @staticmethod
    def _get_provider(name: str) -> PaymentProvider:
        cls = _PROVIDERS.get(name)
        if cls is None:
            raise ProviderError(f"Unknown provider: {name}")
        return cls()

    # ── Orders ────────────────────────────────────────────────

    async def create_order(self, data: OrderCreateIn) -> OrderOut:
        user = await self.user_repo.get_by_id(data.user_id)
        if not user:
            raise OrderNotFound("User not found")

        plan = await self.plan_repo.get_by_id(data.plan_id)
        if not plan or not plan.is_active:
            raise PlanNotPurchasable("Plan is not available")
        if plan.price_rub <= 0:
            raise PlanNotPurchasable("Plan has no price set")

        amount_rub = plan.price_rub
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.order_ttl_minutes
        )

        if data.provider.value == "stars":
            # Stars — no external API; bot handles sendInvoice directly
            external_id = f"stars_{uuid4().hex}"
            payment_url = None
            provider_meta = None
        else:
            provider = self._get_provider(data.provider.value)
            try:
                result = await provider.create_payment(
                    order_id=str(data.user_id),
                    amount_rub=float(amount_rub),
                    description=f"Plan: {plan.name}",
                )
            except Exception as exc:
                raise ProviderError(f"Provider error: {exc}") from exc
            external_id = result.external_id
            payment_url = result.payment_url
            provider_meta = result.provider_meta

        order = await self.order_repo.create(
            OrderInternalCreate(
                user_id=data.user_id,
                plan_id=data.plan_id,
                amount_rub=amount_rub,
                provider=data.provider.value,
                external_id=external_id,
                payment_url=payment_url,
                provider_meta=provider_meta,
                expires_at=expires_at,
            ).model_dump()
        )

        BILLING_ORDER_TOTAL.labels(provider=data.provider.value, status="pending").inc()
        log.info(
            "order_created",
            order_id=str(order.id),
            provider=data.provider.value,
            amount=str(amount_rub),
        )
        return OrderOut.model_validate(order)

    async def get_order(self, order_id: UUID) -> OrderOut:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise OrderNotFound(f"Order {order_id} not found")
        return OrderOut.model_validate(order)

    async def list_user_orders(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> OrderListOut:
        rows, total = await self.order_repo.list_by_user(
            user_id, limit=limit, offset=offset
        )
        return OrderListOut(
            items=[OrderOut.model_validate(o) for o in rows], total=total
        )

    # ── Webhook processing ────────────────────────────────────

    async def process_webhook(self, provider_name: str, request: Request) -> None:
        provider = self._get_provider(provider_name)

        try:
            webhook = await provider.verify_webhook(request)
        except WebhookVerificationFailed:
            raise
        except Exception as exc:
            raise WebhookVerificationFailed(f"Verification error: {exc}") from exc

        order = await self.order_repo.get_by_external_id(webhook.external_id)
        if not order:
            log.warning("webhook_order_not_found", external_id=webhook.external_id)
            raise OrderNotFound(f"Order not found for external_id={webhook.external_id}")

        await self._fulfill_order(order, provider_name, provider_meta=webhook.provider_meta)

    # ── Stars confirmation (called by bot after successful_payment) ──

    async def confirm_stars_payment(
        self,
        order_id: UUID,
        *,
        telegram_payment_charge_id: str,
        total_amount: int,
    ) -> None:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise OrderNotFound(f"Order {order_id} not found")
        if order.provider != "stars":
            raise ProviderError("Order is not a Stars payment")

        meta = json.dumps({
            "telegram_payment_charge_id": telegram_payment_charge_id,
            "total_amount_stars": total_amount,
        })
        await self._fulfill_order(order, "stars", provider_meta=meta)

    # ── Order fulfillment (shared by webhook + stars confirm) ──────

    async def _fulfill_order(
        self,
        order: PaymentOrder,
        provider_name: str,
        *,
        provider_meta: str | None = None,
    ) -> None:
        if order.status in ("paid", "completed"):
            log.info("fulfill_idempotent_skip", order_id=str(order.id))
            return

        if order.status == "expired":
            raise OrderExpired(f"Order {order.id} has expired")

        now = datetime.now(timezone.utc)

        await self.order_repo.update_by_id(
            order.id,
            OrderInternalUpdate(
                status="paid",
                paid_at=now,
                provider_meta=provider_meta or order.provider_meta,
            ).model_dump(exclude_none=True),
        )

        BILLING_ORDER_TOTAL.labels(provider=provider_name, status="paid").inc()
        BILLING_PAYMENT_AMOUNT_RUB_TOTAL.labels(provider=provider_name).inc(
            float(order.amount_rub)
        )

        user = await self._lock_user(order.user_id)
        if not user:
            log.error("fulfill_user_not_found", user_id=str(order.user_id))
            return

        new_balance = user.balance + order.amount_rub
        await self._update_user_balance(user.id, new_balance)
        await self._record_transaction(
            user_id=user.id,
            amount=order.amount_rub,
            balance_after=new_balance,
            tx_type="payment",
            order_id=order.id,
            description=f"Payment via {provider_name}",
        )
        BILLING_BALANCE_OPERATION_TOTAL.labels(type="payment").inc()

        if order.plan_id:
            plan = await self.plan_repo.get_by_id(order.plan_id)
            if plan and plan.is_active and plan.price_rub > 0:
                await self._auto_purchase(user, plan, order, now)

        await self.order_repo.update_by_id(
            order.id,
            OrderInternalUpdate(status="completed", completed_at=now).model_dump(exclude_none=True),
        )
        BILLING_ORDER_TOTAL.labels(provider=provider_name, status="completed").inc()
        log.info("fulfill_completed", order_id=str(order.id))

    # ── Balance operations ────────────────────────────────────

    async def get_balance(self, user_id: UUID) -> BalanceOut:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise OrderNotFound("User not found")
        return BalanceOut(user_id=user.id, balance=user.balance)

    async def credit_balance(self, user_id: UUID, data: BalanceCreditIn) -> BalanceOut:
        user = await self._lock_user(user_id)
        if not user:
            raise OrderNotFound("User not found")

        new_balance = user.balance + data.amount
        await self._update_user_balance(user.id, new_balance)
        await self._record_transaction(
            user_id=user.id,
            amount=data.amount,
            balance_after=new_balance,
            tx_type="manual_credit",
            description=data.description or "Manual credit",
        )
        BILLING_BALANCE_OPERATION_TOTAL.labels(type="manual_credit").inc()
        log.info("balance_credited", user_id=str(user_id), amount=str(data.amount))
        return BalanceOut(user_id=user.id, balance=new_balance)

    async def list_transactions(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> TransactionListOut:
        rows, total = await self.tx_repo.list_by_user(
            user_id, limit=limit, offset=offset
        )
        return TransactionListOut(
            items=[TransactionOut.model_validate(t) for t in rows], total=total
        )

    # ── Internal helpers ──────────────────────────────────────

    async def _lock_user(self, user_id: UUID) -> User | None:
        """SELECT ... FOR UPDATE to prevent concurrent balance modifications."""
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def _update_user_balance(self, user_id: UUID, new_balance: Decimal) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(balance=new_balance)
        )

    async def _record_transaction(
        self,
        *,
        user_id: UUID,
        amount: Decimal,
        balance_after: Decimal,
        tx_type: str,
        order_id: UUID | None = None,
        description: str | None = None,
    ) -> BalanceTransaction:
        return await self.tx_repo.create(
            TransactionInternalCreate(
                user_id=user_id,
                amount=amount,
                balance_after=balance_after,
                type=tx_type,
                order_id=order_id,
                description=description,
            ).model_dump()
        )

    async def _auto_purchase(self, user: User, plan, order: PaymentOrder, now: datetime) -> None:
        """Debit balance and create or extend a subscription."""
        # Re-read balance after lock
        user = await self._lock_user(user.id)
        if not user or user.balance < plan.price_rub:
            log.warning(
                "auto_purchase_insufficient_balance",
                user_id=str(user.id if user else order.user_id),
            )
            return

        new_balance = user.balance - plan.price_rub
        await self._update_user_balance(user.id, new_balance)
        await self._record_transaction(
            user_id=user.id,
            amount=-plan.price_rub,
            balance_after=new_balance,
            tx_type="purchase",
            order_id=order.id,
            description=f"Purchase plan: {plan.name}",
        )
        BILLING_BALANCE_OPERATION_TOTAL.labels(type="purchase").inc()

        # Try to extend existing active subscription with same plan
        existing = await self._find_active_subscription(user.id, plan.id)
        if existing:
            new_expires = (existing.expires_at or now) + timedelta(days=plan.duration_days)
            await self.sub_repo.update_by_id(
                existing.id,
                SubscriptionInternalUpdate(expires_at=new_expires, is_active=True).model_dump(exclude_none=True),
            )
            await self.order_repo.update_by_id(
                order.id,
                OrderInternalUpdate(subscription_id=existing.id).model_dump(exclude_none=True),
            )
            log.info(
                "subscription_extended",
                subscription_id=str(existing.id),
                new_expires=str(new_expires),
            )
        else:
            # Create new subscription
            raw_token = SubscriptionUtils.generate()
            token_hash = SubscriptionUtils.hash(raw_token)
            expires_at = now + timedelta(days=plan.duration_days)

            sub = await self.sub_repo.create(
                SubscriptionInternalCreate(
                    user_id=user.id,
                    plan_id=plan.id,
                    token_hash=token_hash,
                    is_active=True,
                    expires_at=expires_at,
                    hwid_enabled=True,
                    max_devices=plan.max_devices,
                ).model_dump()
            )
            await self.order_repo.update_by_id(
                order.id,
                OrderInternalUpdate(subscription_id=sub.id).model_dump(exclude_none=True),
            )
            log.info(
                "subscription_created",
                subscription_id=str(sub.id),
                expires_at=str(expires_at),
            )

    async def _find_active_subscription(self, user_id: UUID, plan_id: UUID):
        """Find an active subscription for the same user+plan."""
        from services.vpn.subscriptions.model import Subscription

        result = await self.session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.plan_id == plan_id,
                Subscription.is_active == True,
            )
        )
        return result.scalar_one_or_none()


def get_billing_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> BillingService:
    return BillingService(session)
