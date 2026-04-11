from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.billing.exceptions import (
    DeviceSlotLimitExceeded,
    InsufficientBalance,
    OrderExpired,
    OrderNotFound,
    PlanNotPurchasable,
    ProviderError,
    TrialAlreadyUsed,
    TrialUnavailable,
    WebhookVerificationFailed,
)
from services.billing.models import BalanceTransaction, PaymentOrder
from services.billing.providers.base import PaymentProvider
from services.billing.providers.registry import PROVIDERS
from services.billing.repository import OrderRepository, TransactionRepository
from services.bot_notifications.service import TelegramBotNotifyService
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


class BillingService:
    _TELEGRAM_PENDING_MESSAGE_KEY = "_telegram_pending_message"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.order_repo = OrderRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.user_repo = UserRepository(session)
        self.plan_repo = PlanRepository(session)
        self.sub_repo = SubscriptionRepository(session)
        self.settings = get_settings().billing
        self.notify_service = TelegramBotNotifyService()

    @staticmethod
    def _meta_dict(raw: str | None) -> dict[str, object]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except Exception:
            return {"_raw_provider_meta": raw}
        if isinstance(data, dict):
            return data
        return {"_raw_provider_meta": data}

    @classmethod
    def _merge_meta(cls, existing_raw: str | None, patch: dict[str, object]) -> str:
        data = cls._meta_dict(existing_raw)
        data.update(patch)
        return json.dumps(data, default=str)

    @classmethod
    def _merge_meta_strings(cls, existing_raw: str | None, patch_raw: str | None) -> str | None:
        if not existing_raw and not patch_raw:
            return None
        data = cls._meta_dict(existing_raw)
        if patch_raw:
            data.update(cls._meta_dict(patch_raw))
        return json.dumps(data, default=str)

    @classmethod
    def _pending_message_binding(cls, raw: str | None) -> tuple[int, int] | None:
        data = cls._meta_dict(raw)
        binding = data.get(cls._TELEGRAM_PENDING_MESSAGE_KEY)
        if not isinstance(binding, dict):
            return None
        chat_id = binding.get("chat_id")
        message_id = binding.get("message_id")
        if isinstance(chat_id, int) and isinstance(message_id, int):
            return chat_id, message_id
        return None

    @staticmethod
    def _format_rub_short(amount: Decimal) -> str:
        normalized = amount.quantize(Decimal("0.01"))
        if normalized == normalized.to_integral():
            return f"{int(normalized)} ₽"
        return f"{normalized} ₽"

    # ── Provider factory ──────────────────────────────────────

    @staticmethod
    def _get_provider(name: str) -> PaymentProvider:
        cls = PROVIDERS.get(name)
        if cls is None:
            raise ProviderError(f"Unknown provider: {name}")
        return cls()

    # ── Orders ────────────────────────────────────────────────

    async def create_order(self, data: OrderCreateIn) -> OrderOut:
        user = await self.user_repo.get_by_id(data.user_id)
        if not user:
            raise OrderNotFound("User not found")

        order_type = getattr(data, "order_type", None)
        if order_type and order_type.value == "device_slots":
            return await self._create_device_slot_order(data)
        if order_type and order_type.value == "top_up":
            return await self._create_top_up_order(user, data)

        plan = await self.plan_repo.get_by_id(data.plan_id)
        if not plan:
            raise PlanNotPurchasable("Plan is not available")

        renewal_subscription = None
        if data.subscription_id is not None:
            renewal_subscription = await self.sub_repo.get_by_id(data.subscription_id)
            if (
                renewal_subscription is None
                or renewal_subscription.user_id != data.user_id
                or renewal_subscription.plan_id != data.plan_id
            ):
                raise PlanNotPurchasable("Renewal target is not available")

        if not plan.is_active and renewal_subscription is None:
            raise PlanNotPurchasable("Plan is not available")

        is_free = plan.price_rub <= 0

        if is_free and data.provider.value != "free":
            raise PlanNotPurchasable("Free plan requires provider='free'")
        if not is_free and data.provider.value == "free":
            raise PlanNotPurchasable("Paid plan cannot use provider='free'")

        if is_free:
            already_used = await self.order_repo.has_completed_order_for_plan(
                data.user_id, plan.id,
            )
            if already_used:
                raise TrialAlreadyUsed("Free trial already used")
            if await self._has_live_subscription(data.user_id):
                raise TrialUnavailable("Free trial is unavailable while an active subscription exists")
            if await self.order_repo.has_completed_paid_order(data.user_id):
                raise TrialUnavailable("Free trial is unavailable after a paid purchase")
            return await self._create_free_order(user, plan, data)

        extra_devices = getattr(data, "device_slots_qty", 0) or 0
        device_price = getattr(plan, "device_price_rub", Decimal("0")) or Decimal("0")
        amount_rub = plan.price_rub + extra_devices * device_price
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.order_ttl_minutes
        )

        description = f"Plan: {plan.name}"
        if extra_devices > 0:
            description += f" + {extra_devices} device(s)"

        if data.provider.value == "balance":
            return await self._create_balance_plan_order(
                user=user,
                plan=plan,
                data=data,
                amount_rub=amount_rub,
                extra_devices=extra_devices,
            )

        if data.provider.value == "stars":
            external_id = f"stars_{uuid4().hex}"
            payment_url = None
            provider_meta = None
        else:
            provider = self._get_provider(data.provider.value)
            try:
                result = await provider.create_payment(
                    order_id=str(data.user_id),
                    amount_rub=float(amount_rub),
                    description=description,
                    payment_method=data.payment_method,
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
                subscription_id=data.subscription_id,
                order_type=data.order_type.value,
                device_slots_qty=extra_devices,
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

    async def _create_free_order(self, user: User, plan, data: OrderCreateIn) -> OrderOut:
        """Create and immediately fulfill a free plan order."""
        now = datetime.now(timezone.utc)
        order = await self.order_repo.create(
            OrderInternalCreate(
                user_id=data.user_id,
                plan_id=plan.id,
                amount_rub=Decimal("0"),
                provider="free",
                status="paid",
                external_id=f"free_{uuid4().hex}",
                payment_url=None,
                order_type="plan_purchase",
                device_slots_qty=0,
            ).model_dump()
        )

        # Auto-purchase subscription (no balance operations needed)
        await self._auto_purchase_free(user, plan, order, now)

        await self.order_repo.update_by_id(
            order.id,
            OrderInternalUpdate(
                status="completed",
                paid_at=now,
                completed_at=now,
            ).model_dump(exclude_none=True),
        )

        BILLING_ORDER_TOTAL.labels(provider="free", status="completed").inc()
        log.info("free_order_completed", order_id=str(order.id), plan=plan.name)

        refreshed = await self.order_repo.get_by_id(order.id)
        return OrderOut.model_validate(refreshed)

    async def _create_top_up_order(self, user: User, data: OrderCreateIn) -> OrderOut:
        amount_rub = getattr(data, "amount_rub", None)
        if amount_rub is None or amount_rub <= 0:
            raise PlanNotPurchasable("Top up amount must be greater than zero")

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.order_ttl_minutes
        )
        description = f"Balance top-up for user {user.id}"

        if data.provider.value == "stars":
            external_id = f"stars_{uuid4().hex}"
            payment_url = None
            provider_meta = None
        else:
            provider = self._get_provider(data.provider.value)
            try:
                result = await provider.create_payment(
                    order_id=str(data.user_id),
                    amount_rub=float(amount_rub),
                    description=description,
                    payment_method=data.payment_method,
                )
            except Exception as exc:
                raise ProviderError(f"Provider error: {exc}") from exc
            external_id = result.external_id
            payment_url = result.payment_url
            provider_meta = result.provider_meta

        order = await self.order_repo.create(
            OrderInternalCreate(
                user_id=data.user_id,
                plan_id=None,
                amount_rub=amount_rub,
                provider=data.provider.value,
                external_id=external_id,
                payment_url=payment_url,
                provider_meta=provider_meta,
                expires_at=expires_at,
                subscription_id=None,
                order_type="top_up",
                device_slots_qty=0,
            ).model_dump()
        )

        BILLING_ORDER_TOTAL.labels(provider=data.provider.value, status="pending").inc()
        log.info(
            "top_up_order_created",
            order_id=str(order.id),
            provider=data.provider.value,
            amount=str(amount_rub),
        )
        return OrderOut.model_validate(order)

    async def _create_device_slot_order(self, data: OrderCreateIn) -> OrderOut:
        if not data.subscription_id:
            raise OrderNotFound("subscription_id is required for device_slots order")
        sub = await self.sub_repo.get_by_id(data.subscription_id)
        if not sub or not sub.is_active:
            raise OrderNotFound("Active subscription not found")

        plan = await self.plan_repo.get_by_id(sub.plan_id) if sub.plan_id else None
        if not plan:
            raise PlanNotPurchasable("Subscription has no plan")

        qty = data.device_slots_qty
        included = getattr(plan, "included_devices", 1)
        paid = getattr(sub, "paid_device_slots", 0)
        max_allowed = plan.max_devices - included - paid
        if qty > max_allowed:
            raise DeviceSlotLimitExceeded(
                f"Cannot add {qty} slots, max purchasable: {max_allowed}"
            )

        device_price = getattr(plan, "device_price_rub", Decimal("0")) or Decimal("0")
        if device_price <= 0:
            raise PlanNotPurchasable("Plan has no device price set")

        amount_rub = qty * device_price
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.order_ttl_minutes
        )
        description = f"{qty} device slot(s) for {plan.name}"

        if data.provider.value == "balance":
            return await self._create_balance_device_slot_order(
                user_id=data.user_id,
                subscription_id=data.subscription_id,
                qty=qty,
                amount_rub=amount_rub,
            )

        if data.provider.value == "stars":
            external_id = f"stars_{uuid4().hex}"
            payment_url = None
            provider_meta = None
        else:
            provider = self._get_provider(data.provider.value)
            try:
                result = await provider.create_payment(
                    order_id=str(data.user_id),
                    amount_rub=float(amount_rub),
                    description=description,
                    payment_method=data.payment_method,
                )
            except Exception as exc:
                raise ProviderError(f"Provider error: {exc}") from exc
            external_id = result.external_id
            payment_url = result.payment_url
            provider_meta = result.provider_meta

        order = await self.order_repo.create(
            OrderInternalCreate(
                user_id=data.user_id,
                plan_id=None,
                amount_rub=amount_rub,
                provider=data.provider.value,
                external_id=external_id,
                payment_url=payment_url,
                provider_meta=provider_meta,
                expires_at=expires_at,
                order_type="device_slots",
                device_slots_qty=qty,
            ).model_dump()
        )
        # Store subscription_id on order
        await self.order_repo.update_by_id(
            order.id,
            OrderInternalUpdate(subscription_id=data.subscription_id).model_dump(exclude_none=True),
        )

        BILLING_ORDER_TOTAL.labels(provider=data.provider.value, status="pending").inc()
        log.info(
            "device_slot_order_created",
            order_id=str(order.id),
            qty=qty,
            amount=str(amount_rub),
        )
        # Re-fetch to include subscription_id
        refreshed = await self.order_repo.get_by_id(order.id)
        return OrderOut.model_validate(refreshed)

    async def _create_balance_plan_order(
        self,
        *,
        user: User,
        plan,
        data: OrderCreateIn,
        amount_rub: Decimal,
        extra_devices: int,
    ) -> OrderOut:
        now = datetime.now(timezone.utc)
        order = await self.order_repo.create(
            OrderInternalCreate(
                user_id=data.user_id,
                plan_id=data.plan_id,
                amount_rub=amount_rub,
                provider="balance",
                status="paid",
                external_id=f"balance_{uuid4().hex}",
                payment_url=None,
                provider_meta=None,
                expires_at=None,
                subscription_id=data.subscription_id,
                order_type=data.order_type.value,
                device_slots_qty=extra_devices,
            ).model_dump()
        )
        await self._auto_purchase(user, plan, order, now, strict_balance=True)
        await self.order_repo.update_by_id(
            order.id,
            OrderInternalUpdate(status="completed", paid_at=now, completed_at=now).model_dump(exclude_none=True),
        )
        BILLING_ORDER_TOTAL.labels(provider="balance", status="completed").inc()
        refreshed = await self.order_repo.get_by_id(order.id)
        return OrderOut.model_validate(refreshed)

    async def _create_balance_device_slot_order(
        self,
        *,
        user_id: UUID,
        subscription_id: UUID,
        qty: int,
        amount_rub: Decimal,
    ) -> OrderOut:
        now = datetime.now(timezone.utc)
        order = await self.order_repo.create(
            OrderInternalCreate(
                user_id=user_id,
                plan_id=None,
                amount_rub=amount_rub,
                provider="balance",
                status="paid",
                external_id=f"balance_{uuid4().hex}",
                payment_url=None,
                provider_meta=None,
                expires_at=None,
                subscription_id=subscription_id,
                order_type="device_slots",
                device_slots_qty=qty,
            ).model_dump()
        )
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise OrderNotFound("User not found")
        await self._fulfill_device_slots(user, order, now, strict_balance=True)
        await self.order_repo.update_by_id(
            order.id,
            OrderInternalUpdate(status="completed", paid_at=now, completed_at=now).model_dump(exclude_none=True),
        )
        BILLING_ORDER_TOTAL.labels(provider="balance", status="completed").inc()
        refreshed = await self.order_repo.get_by_id(order.id)
        return OrderOut.model_validate(refreshed)

    async def get_order(self, order_id: UUID) -> OrderOut:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise OrderNotFound(f"Order {order_id} not found")
        return OrderOut.model_validate(order)

    async def update_order_metadata(
        self,
        *,
        order_id: UUID,
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> None:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise OrderNotFound(f"Order {order_id} not found")
        patch: dict[str, object] = {}
        if telegram_chat_id is not None and telegram_message_id is not None:
            patch[self._TELEGRAM_PENDING_MESSAGE_KEY] = {
                "chat_id": int(telegram_chat_id),
                "message_id": int(telegram_message_id),
            }
        if not patch:
            return
        await self.order_repo.update_by_id(
            order.id,
            OrderInternalUpdate(
                provider_meta=self._merge_meta(order.provider_meta, patch),
            ).model_dump(exclude_none=True),
        )

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
        if webhook.amount_rub > 0:
            order_amount = Decimal(str(order.amount_rub))
            webhook_amount = Decimal(str(webhook.amount_rub))
            if order_amount != webhook_amount:
                raise WebhookVerificationFailed(
                    f"Amount mismatch for external_id={webhook.external_id}"
                )

        if not getattr(webhook, "should_fulfill", True):
            patch: dict[str, object] = {
                "provider_meta": self._merge_meta_strings(order.provider_meta, webhook.provider_meta),
            }
            provider_status = str(getattr(webhook, "provider_status", "") or "").upper()
            if provider_status == "CANCELED" and order.status == "pending":
                patch["status"] = "expired"
            await self.order_repo.update_by_id(order.id, OrderInternalUpdate(**patch).model_dump(exclude_none=True))
            log.info(
                "webhook_non_paid_event",
                provider=provider_name,
                order_id=str(order.id),
                external_id=webhook.external_id,
                provider_status=webhook.provider_status,
            )
            return

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
                provider_meta=self._merge_meta_strings(order.provider_meta, provider_meta),
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

        if getattr(order, "order_type", "plan_purchase") == "device_slots":
            await self._fulfill_device_slots(user, order, now)
        elif order.plan_id:
            plan = await self.plan_repo.get_by_id(order.plan_id)
            if plan and plan.is_active and plan.price_rub > 0:
                await self._auto_purchase(user, plan, order, now)

        await self.order_repo.update_by_id(
            order.id,
            OrderInternalUpdate(status="completed", completed_at=now).model_dump(exclude_none=True),
        )
        BILLING_ORDER_TOTAL.labels(provider=provider_name, status="completed").inc()

        # Referral reward: trigger after first paid order (plan_purchase or renewal)
        order_type = getattr(order, "order_type", "plan_purchase")
        if order_type in ("plan_purchase", "subscription_renewal") and provider_name != "free":
            try:
                from services.referral.service import ReferralService
                referral_service = ReferralService(self.session)
                await referral_service.process_reward_if_eligible(order.user_id)
            except Exception:
                log.exception("referral_reward_failed", user_id=str(order.user_id))

        if provider_name != "stars":
            updated_order = await self.order_repo.get_by_id(order.id)
            pending_message = self._pending_message_binding(
                getattr(updated_order, "provider_meta", None),
            )
            asyncio.create_task(
                self._notify_order_fulfilled(
                    chat_id=user.telegram_id,
                    order_type=order_type,
                    pending_message=pending_message,
                    balance_rub=self._format_rub_short(new_balance),
                )
            )
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

    async def _find_active_subscription_for_plan(self, user_id: UUID, plan_id: UUID):
        subscriptions = await self.sub_repo.list_by_user_id(user_id, active_only=True)
        return next((sub for sub in subscriptions if sub.plan_id == plan_id), None)

    async def _notify_order_fulfilled(
        self,
        *,
        chat_id: int,
        order_type: str,
        pending_message: tuple[int, int] | None,
        balance_rub: str,
    ):
        try:
            await self.notify_service.send_payment_completed(
                chat_id=chat_id,
                order_type=order_type,
                pending_message=None if order_type == "top_up" else pending_message,
            )
            if order_type == "top_up":
                await self.notify_service.replace_pending_with_wallet(
                    balance_rub=balance_rub,
                    pending_message=pending_message,
                )
        except Exception:
            log.exception(
                "notify_order_fulfilled_failed",
                chat_id=str(chat_id),
                order_type=order_type,
            )

    async def _has_live_subscription(self, user_id: UUID) -> bool:
        now = datetime.now(timezone.utc)
        subscriptions = await self.sub_repo.list_by_user_id(user_id, active_only=True)
        for sub in subscriptions:
            if sub.expires_at is None or sub.expires_at > now:
                return True
        return False

    async def _auto_purchase_free(self, user: User, plan, order: PaymentOrder, now: datetime) -> None:
        """Create subscription for a free plan without any balance operations."""
        existing = await self._find_active_subscription_for_plan(user.id, plan.id)
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
            log.info("free_subscription_extended", subscription_id=str(existing.id))
        else:
            raw_token = SubscriptionUtils.generate()
            token_hash = SubscriptionUtils.hash(raw_token)
            expires_at = now + timedelta(days=plan.duration_days)
            included = getattr(plan, "included_devices", 1)

            sub = await self.sub_repo.create(
                SubscriptionInternalCreate(
                    user_id=user.id,
                    plan_id=plan.id,
                    token_hash=token_hash,
                    is_active=True,
                    expires_at=expires_at,
                    hwid_enabled=True,
                    max_devices=included,
                    paid_device_slots=0,
                ).model_dump()
            )
            await self.order_repo.update_by_id(
                order.id,
                OrderInternalUpdate(subscription_id=sub.id).model_dump(exclude_none=True),
            )
            log.info("free_subscription_created", subscription_id=str(sub.id), expires_at=str(expires_at))

    async def _auto_purchase(
        self,
        user: User,
        plan,
        order: PaymentOrder,
        now: datetime,
        *,
        strict_balance: bool = False,
    ) -> None:
        """Debit balance and create or extend a subscription."""
        extra_devices = getattr(order, "device_slots_qty", 0) or 0
        device_price = getattr(plan, "device_price_rub", Decimal("0")) or Decimal("0")
        total_price = plan.price_rub + extra_devices * device_price

        # Re-read balance after lock
        user = await self._lock_user(user.id)
        if not user or user.balance < total_price:
            log.warning(
                "auto_purchase_insufficient_balance",
                user_id=str(user.id if user else order.user_id),
            )
            if strict_balance:
                raise InsufficientBalance("Insufficient balance")
            return

        new_balance = user.balance - total_price
        await self._update_user_balance(user.id, new_balance)

        desc = f"Purchase plan: {plan.name}"
        if extra_devices > 0:
            desc += f" + {extra_devices} device slot(s)"
        await self._record_transaction(
            user_id=user.id,
            amount=-total_price,
            balance_after=new_balance,
            tx_type="purchase",
            order_id=order.id,
            description=desc,
        )
        BILLING_BALANCE_OPERATION_TOTAL.labels(type="purchase").inc()

        # Renewal should extend the current subscription even if it expired or was deactivated.
        existing = None
        if getattr(order, "order_type", "plan_purchase") == "subscription_renewal" and order.subscription_id:
            existing = await self.sub_repo.get_by_id(order.subscription_id)
            if existing and (existing.user_id != user.id or existing.plan_id != plan.id):
                existing = None
        if existing is None:
            existing = await self._find_active_subscription_for_plan(user.id, plan.id)

        if existing:
            base_expires = existing.expires_at if existing.expires_at and existing.expires_at > now else now
            new_expires = base_expires + timedelta(days=plan.duration_days)
            update_data = SubscriptionInternalUpdate(
                expires_at=new_expires, is_active=True,
            )
            if extra_devices > 0:
                update_data.paid_device_slots = (getattr(existing, "paid_device_slots", 0) or 0) + extra_devices
            await self.sub_repo.update_by_id(
                existing.id,
                update_data.model_dump(exclude_none=True),
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
            included = getattr(plan, "included_devices", 1)

            sub = await self.sub_repo.create(
                SubscriptionInternalCreate(
                    user_id=user.id,
                    plan_id=plan.id,
                    token_hash=token_hash,
                    is_active=True,
                    expires_at=expires_at,
                    hwid_enabled=True,
                    max_devices=included + extra_devices,
                    paid_device_slots=extra_devices,
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

    async def _fulfill_device_slots(
        self,
        user: User,
        order: PaymentOrder,
        now: datetime,
        *,
        strict_balance: bool = False,
    ) -> None:
        """Debit balance and add device slots to subscription."""
        user = await self._lock_user(user.id)
        if not user or user.balance < order.amount_rub:
            log.warning(
                "device_slots_insufficient_balance",
                user_id=str(user.id if user else order.user_id),
            )
            if strict_balance:
                raise InsufficientBalance("Insufficient balance")
            return

        new_balance = user.balance - order.amount_rub
        await self._update_user_balance(user.id, new_balance)
        await self._record_transaction(
            user_id=user.id,
            amount=-order.amount_rub,
            balance_after=new_balance,
            tx_type="device_slot_purchase",
            order_id=order.id,
            description=f"Purchase {order.device_slots_qty} device slot(s)",
        )
        BILLING_BALANCE_OPERATION_TOTAL.labels(type="device_slot_purchase").inc()

        if order.subscription_id:
            sub = await self.sub_repo.get_by_id(order.subscription_id)
            if sub:
                new_paid = (getattr(sub, "paid_device_slots", 0) or 0) + order.device_slots_qty
                await self.sub_repo.update_by_id(
                    sub.id,
                    SubscriptionInternalUpdate(paid_device_slots=new_paid).model_dump(exclude_none=True),
                )
                log.info(
                    "device_slots_added",
                    subscription_id=str(sub.id),
                    qty=order.device_slots_qty,
                    total_paid=new_paid,
                )


def get_billing_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> BillingService:
    return BillingService(session)
