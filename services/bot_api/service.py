from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_status.service import AdminStatusService
from services.config import get_settings
from services.billing.repository import OrderRepository
from services.billing.schemas import OrderCreateIn, OrderOut, OrderTypeEnum, PaymentProviderEnum
from services.billing.service import BillingService
from services.plans.repository import PlanRepository
from services.plans.schemas import PlanOut
from services.users.repository import UserRepository
from services.users.schemas import UserCreateIn, UserOut, UserUpdateIn
from services.users.service import UserService
from services.vpn.subscriptions.repository import SubscriptionDeviceRepository, SubscriptionRepository
from services.vpn.subscriptions.schemas import SubscriptionDeviceOut, SubscriptionOut
from services.vpn.subscriptions.service import SubscriptionService
from shared.database.session import AsyncDatabase
from shared.redis.client import RedisClient, get_redis_client

from .schemas import (
    BotAction,
    BotDashboardState,
    BotDeviceOut,
    BotDevicesOut,
    BotDeviceSlotPurchaseIn,
    BotOrderActionOut,
    BotOrderCreateIn,
    BotOrderHistoryItemOut,
    BotOrderHistoryOut,
    BotOrderUpdateIn,
    BotOrderOut,
    BotPlanListOut,
    BotRenewOfferOut,
    BotRenewOrderIn,
    BotTopUpCreateIn,
    BotUserOut,
    BotPlanOut,
    BotServiceHealth,
    BotServiceStatusOut,
    BotSessionOut,
    BotSessionSyncIn,
    BotStarsConfirmIn,
    BotSubscriptionLinkOut,
    BotSubscriptionSummaryOut,
)
from ..billing.exceptions import InsufficientBalance, ProviderError

log = logging.getLogger(__name__)


class BotApiService:
    def __init__(self, session: AsyncSession, redis: RedisClient):
        self.session = session
        self.user_repository = UserRepository(session)
        self.order_repository = OrderRepository(session)
        self.plan_repository = PlanRepository(session)
        self.subscription_repository = SubscriptionRepository(session)
        self.device_repository = SubscriptionDeviceRepository(session)
        self.user_service = UserService(session)
        self.billing_service = BillingService(session)
        self.subscription_service = SubscriptionService(session, redis)
        self.admin_status_service = AdminStatusService(session)
        self.settings = get_settings()

    async def sync_session(self, payload: BotSessionSyncIn) -> BotSessionOut:
        user, is_new_user = await self._ensure_user(payload)
        return await self._build_session(user=user, is_new_user=is_new_user)

    async def accept_terms(self, payload: BotSessionSyncIn) -> BotSessionOut:
        user, is_new_user = await self._ensure_user(payload)
        if not user.terms_accepted:
            user = await self.user_service.update_user(
                user.id,
                UserUpdateIn(
                    terms_accepted=True,
                    terms_accepted_at=datetime.now(timezone.utc),
                ),
            )
        return await self._build_session(user=user, is_new_user=is_new_user)

    async def list_plans(self, *, telegram_id: int | None = None) -> BotPlanListOut:
        current_plan_id: UUID | None = None
        used_trial_plan_ids: list[UUID] = []
        hide_free_plans = False
        user = None
        if telegram_id is not None:
            user = await self.user_repository.get_by_telegram_id(telegram_id)
            if user is not None:
                subscription = await self._current_subscription(user.id)
                if subscription is not None:
                    current_plan_id = subscription.plan_id
                    if subscription.is_active and (subscription.expires_at is None or subscription.expires_at > datetime.now(timezone.utc)):
                        hide_free_plans = True

        rows, total = await self.plan_repository.list_all(active_only=True)
        hidden_plan_name = self.settings.migration.gift_plan_name if self.settings.migration.enabled else ""
        if hidden_plan_name:
            rows = [plan for plan in rows if plan.name != hidden_plan_name]
            total = len(rows)

        if user is not None:
            if not hide_free_plans:
                hide_free_plans = await self.order_repository.has_completed_paid_order(user.id)
            filtered_rows = []
            for plan in rows:
                if plan.price_rub <= 0:
                    used = await self.order_repository.has_completed_order_for_plan(
                        user.id, plan.id,
                    )
                    if used:
                        used_trial_plan_ids.append(plan.id)
                    if used or hide_free_plans:
                        continue
                filtered_rows.append(plan)
            rows = filtered_rows
            total = len(rows)

        items = [
            BotPlanOut(
                **PlanOut.model_validate(plan).model_dump(),
                is_current=plan.id == current_plan_id,
            )
            for plan in rows
        ]
        return BotPlanListOut(
            items=items,
            total=total,
            current_plan_id=current_plan_id,
            used_trial_plan_ids=used_trial_plan_ids,
        )

    async def create_order(self, *, telegram_id: int, payload: BotOrderCreateIn) -> BotOrderActionOut:
        from services.billing.exceptions import ActiveSubscriptionExists, InsufficientBalance, PlanNotPurchasable, ProviderError, TrialAlreadyUsed, TrialUnavailable
        user = await self._require_user_by_telegram_id(telegram_id)
        extra = getattr(payload, "extra_devices", 0) or 0
        try:
            order = await self.billing_service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    plan_id=payload.plan_id,
                    provider=payload.provider,
                    device_slots_qty=extra,
                )
            )
        except TrialAlreadyUsed:
            raise HTTPException(status_code=409, detail="Trial already used")
        except (ActiveSubscriptionExists, TrialUnavailable):
            raise HTTPException(status_code=409, detail="Trial unavailable")
        except InsufficientBalance as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PlanNotPurchasable as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        session = await self._build_session(
            user=user,
            forced_pending_order=order if order.status == "pending" else None,
        )
        return BotOrderActionOut(order=BotOrderOut.model_validate(order), session=session)

    async def claim_migration_gift(self, *, telegram_id: int) -> BotOrderActionOut:
        from services.billing.exceptions import (
            ActiveSubscriptionExists,
            PlanNotPurchasable,
            TrialAlreadyUsed,
            TrialUnavailable,
        )

        if not self.settings.migration.enabled or not self.settings.migration.gift_plan_name:
            raise HTTPException(status_code=404, detail="Migration gift is unavailable")

        user = await self._require_user_by_telegram_id(telegram_id)
        plan = await self.plan_repository.get_by_name(self.settings.migration.gift_plan_name)
        if plan is None or not plan.is_active or plan.price_rub > 0:
            raise HTTPException(status_code=404, detail="Migration gift plan not found")

        try:
            order = await self.billing_service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    plan_id=plan.id,
                    provider=PaymentProviderEnum.FREE,
                )
            )
        except TrialAlreadyUsed:
            raise HTTPException(status_code=409, detail="Gift already claimed")
        except (ActiveSubscriptionExists, TrialUnavailable) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PlanNotPurchasable as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        session = await self._build_session(
            user=user,
            forced_pending_order=order if order.status == "pending" else None,
        )
        return BotOrderActionOut(order=BotOrderOut.model_validate(order), session=session)

    async def get_order(self, *, telegram_id: int, order_id: UUID) -> BotOrderActionOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        order = await self.billing_service.get_order(order_id)
        if order.user_id != user.id:
            raise HTTPException(status_code=404, detail="Order not found")
        session = await self._build_session(user=user, forced_pending_order=order if order.status == "pending" else None)
        return BotOrderActionOut(order=BotOrderOut.model_validate(order), session=session)

    async def update_order_metadata(
        self,
        *,
        telegram_id: int,
        order_id: UUID,
        payload: BotOrderUpdateIn,
    ) -> None:
        user = await self._require_user_by_telegram_id(telegram_id)
        order = await self.billing_service.get_order(order_id)
        if order.user_id != user.id:
            raise HTTPException(status_code=404, detail="Order not found")
        await self.billing_service.update_order_metadata(
            order_id=order.id,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_message_id=payload.telegram_message_id,
        )

    async def get_renew_offer(self, *, telegram_id: int) -> BotRenewOfferOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        subscription = await self._current_subscription(user.id)
        if subscription is None or subscription.plan_id is None:
            raise HTTPException(status_code=404, detail="Subscription not found")

        status = self._classify_subscription(subscription)
        if status not in {
            BotDashboardState.ACTIVE,
            BotDashboardState.EXPIRING,
            BotDashboardState.EXPIRED,
            BotDashboardState.INACTIVE,
        }:
            raise HTTPException(status_code=409, detail="Subscription cannot be renewed")

        plan = await self.plan_repository.get_by_id(subscription.plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")

        now = datetime.now(timezone.utc)
        current_expires_at = subscription.expires_at
        if current_expires_at and current_expires_at > now:
            renewed_expires_at = current_expires_at + timedelta(days=plan.duration_days)
        else:
            renewed_expires_at = now + timedelta(days=plan.duration_days)

        providers = [
            PaymentProviderEnum.PLATEGA,
            PaymentProviderEnum.CRYPTO,
        ]
        if user.balance >= plan.price_rub:
            providers.append(PaymentProviderEnum.BALANCE)
        if getattr(plan, "price_stars", None):
            providers.append(PaymentProviderEnum.STARS)

        return BotRenewOfferOut(
            subscription_id=subscription.id,
            plan_id=plan.id,
            plan_name=plan.name,
            status=status,
            duration_days=plan.duration_days,
            price_rub=plan.price_rub,
            price_stars=getattr(plan, "price_stars", None),
            current_expires_at=current_expires_at,
            renewed_expires_at=renewed_expires_at,
            providers=providers,
            is_reactivation=status in {BotDashboardState.EXPIRED, BotDashboardState.INACTIVE},
        )

    async def create_renew_order(self, *, telegram_id: int, payload: BotRenewOrderIn) -> BotOrderActionOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        subscription = await self._current_subscription(user.id)
        if subscription is None or subscription.plan_id is None:
            raise HTTPException(status_code=404, detail="Subscription not found")

        status = self._classify_subscription(subscription)
        if status not in {
            BotDashboardState.ACTIVE,
            BotDashboardState.EXPIRING,
            BotDashboardState.EXPIRED,
            BotDashboardState.INACTIVE,
        }:
            raise HTTPException(status_code=409, detail="Subscription cannot be renewed")

        plan = await self.plan_repository.get_by_id(subscription.plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        if payload.provider == PaymentProviderEnum.STARS and not getattr(plan, "price_stars", None):
            raise HTTPException(status_code=400, detail="Stars not available for current plan")

        try:
            order = await self.billing_service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    plan_id=subscription.plan_id,
                    provider=payload.provider,
                    order_type=OrderTypeEnum.SUBSCRIPTION_RENEWAL,
                    subscription_id=subscription.id,
                )
            )
        except InsufficientBalance as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        session = await self._build_session(
            user=user,
            forced_pending_order=order if order.status == "pending" else None,
        )
        return BotOrderActionOut(order=BotOrderOut.model_validate(order), session=session)

    async def create_top_up_order(self, *, telegram_id: int, payload: BotTopUpCreateIn) -> BotOrderActionOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        try:
            order = await self.billing_service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    provider=payload.provider,
                    amount_rub=payload.amount,
                    order_type=OrderTypeEnum.TOP_UP,
                )
            )
        except ProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        session = await self._build_session(user=user, forced_pending_order=order if order.status == "pending" else None)
        return BotOrderActionOut(order=BotOrderOut.model_validate(order), session=session)

    async def purchase_device_slots(
        self, *, telegram_id: int, payload: BotDeviceSlotPurchaseIn,
    ) -> BotOrderActionOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        subscription = await self._current_subscription(user.id)
        if subscription is None:
            raise HTTPException(status_code=404, detail="Active subscription not found")
        try:
            order = await self.billing_service.create_order(
                OrderCreateIn(
                    user_id=user.id,
                    provider=payload.provider,
                    order_type=OrderTypeEnum.DEVICE_SLOTS,
                    device_slots_qty=payload.qty,
                    subscription_id=subscription.id,
                )
            )
        except InsufficientBalance as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        session = await self._build_session(user=user, forced_pending_order=order if order.status == "pending" else None)
        return BotOrderActionOut(order=BotOrderOut.model_validate(order), session=session)

    async def list_devices(self, *, telegram_id: int) -> BotDevicesOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        session = await self._build_session(user=user)
        if session.subscription is None:
            return BotDevicesOut(session=session, items=[], total=0, active_total=0)

        devices = await self.subscription_service.list_devices(
            session.subscription.id,
            active_only=False,
        )
        items = self._to_bot_devices(devices)
        active_total = sum(1 for item in items if item.is_active)
        return BotDevicesOut(
            session=session,
            items=items,
            total=len(items),
            active_total=active_total,
        )

    async def revoke_device(self, *, telegram_id: int, device_id: UUID) -> BotDevicesOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        subscription = await self._current_subscription(user.id)
        if subscription is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        await self.subscription_service.revoke_device(subscription.id, device_id)
        return await self.list_devices(telegram_id=telegram_id)

    async def confirm_stars_payment(
        self,
        *,
        telegram_id: int,
        order_id: UUID,
        payload: BotStarsConfirmIn,
    ) -> BotOrderActionOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        order = await self.billing_service.get_order(order_id)
        if order.user_id != user.id:
            raise HTTPException(status_code=404, detail="Order not found")

        await self.billing_service.confirm_stars_payment(
            order_id,
            telegram_payment_charge_id=payload.telegram_payment_charge_id,
            total_amount=payload.total_amount,
        )
        updated_order = await self.billing_service.get_order(order_id)
        session = await self._build_session(user=user)
        return BotOrderActionOut(order=BotOrderOut.model_validate(updated_order), session=session)

    async def list_user_orders(self, *, telegram_id: int) -> BotOrderHistoryOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        rows, total = await self.order_repository.list_by_user(user.id, limit=50, offset=0)
        plan_ids = {row.plan_id for row in rows if row.plan_id}
        plan_names: dict[UUID, str] = {}
        for plan_id in plan_ids:
            plan = await self.plan_repository.get_by_id(plan_id)
            if plan is not None:
                plan_names[plan_id] = plan.name
        items = [
            BotOrderHistoryItemOut(
                id=row.id,
                plan_name=plan_names.get(row.plan_id) if row.plan_id else None,
                amount_rub=row.amount_rub,
                provider=row.provider,
                status=row.status,
                order_type=getattr(row, "order_type", "plan_purchase"),
                device_slots_qty=getattr(row, "device_slots_qty", 0),
                paid_at=row.paid_at,
                completed_at=row.completed_at,
                created_at=row.created_at,
            )
            for row in rows
        ]
        return BotOrderHistoryOut(items=items, total=total)

    async def issue_subscription_link(self, *, telegram_id: int) -> BotSubscriptionLinkOut:
        user = await self._require_user_by_telegram_id(telegram_id)
        subscription = await self._current_subscription(user.id)
        if subscription is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if self._classify_subscription(subscription) not in {
            BotDashboardState.ACTIVE,
            BotDashboardState.EXPIRING,
        }:
            raise HTTPException(status_code=409, detail="Subscription is not active")

        rotated = await self.subscription_service.rotate_token(subscription.id)
        subscription_url = await self._encrypt_subscription_url_for_happ(
            rotated.subscription_url,
        )
        session = await self._build_session(user=user)
        return BotSubscriptionLinkOut(subscription_url=subscription_url, session=session)

    async def _ensure_user(self, payload: BotSessionSyncIn) -> tuple[UserOut, bool]:
        existing = await self.user_repository.get_by_telegram_id(payload.telegram_id)
        desired_tag = payload.first_name or None
        desired_description = " ".join(
            part for part in [payload.first_name, payload.last_name] if part
        ) or None

        if existing is None:
            created = await self.user_service.create_user(
                UserCreateIn(
                    telegram_id=payload.telegram_id,
                    username=payload.username,
                    tag=desired_tag,
                    description=desired_description,
                )
            )
            return created, True

        patch: dict[str, object] = {}
        if existing.username != payload.username:
            patch["username"] = payload.username
        if existing.tag != desired_tag:
            patch["tag"] = desired_tag
        if existing.description != desired_description:
            patch["description"] = desired_description

        if patch:
            updated = await self.user_service.update_user(existing.id, UserUpdateIn(**patch))
            return updated, False
        return UserOut.model_validate(existing), False

    async def _require_user_by_telegram_id(
        self,
        telegram_id: int,
        *,
        require_terms: bool = True,
    ) -> UserOut:
        user = await self.user_repository.get_by_telegram_id(telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if require_terms and not user.terms_accepted:
            raise HTTPException(status_code=403, detail="Terms not accepted")
        return UserOut.model_validate(user)

    async def _build_session(
        self,
        *,
        user: UserOut,
        is_new_user: bool = False,
        forced_pending_order: OrderOut | None = None,
    ) -> BotSessionOut:
        orders = await self._list_orders(user.id)
        pending_order = forced_pending_order or self._pick_pending_order(orders)
        subscription = await self._build_subscription_summary(user.id, orders=orders)
        service = await self._build_service_status()

        state = BotDashboardState.NO_SUBSCRIPTION
        if subscription is not None:
            state = subscription.status
        elif pending_order is not None:
            state = BotDashboardState.PENDING_PAYMENT
        elif is_new_user:
            state = BotDashboardState.NEW

        return BotSessionOut(
            user=BotUserOut.model_validate(user),
            state=state,
            is_new_user=is_new_user,
            subscription=subscription,
            pending_order=BotOrderOut.model_validate(pending_order) if pending_order is not None else None,
            service=service,
            available_actions=(
                []
                if not user.terms_accepted
                else self._available_actions(
                    state=state,
                    subscription=subscription,
                    pending_order=pending_order,
                )
            ),
        )

    async def _build_subscription_summary(
        self,
        user_id: UUID,
        *,
        orders: list[OrderOut],
    ) -> BotSubscriptionSummaryOut | None:
        subscription = await self._current_subscription(user_id)
        if subscription is None:
            return None

        plan = await self.plan_repository.get_by_id(subscription.plan_id) if subscription.plan_id else None
        active_devices = await self.subscription_service.list_devices(subscription.id, active_only=True)

        paid_slots = getattr(subscription, "paid_device_slots", 0) or 0
        if plan is not None:
            included = getattr(plan, "included_devices", 1)
            effective_limit = included + paid_slots
            max_purchasable = plan.max_devices - included - paid_slots
            device_price_rub = getattr(plan, "device_price_rub", 0)
            device_price_stars = getattr(plan, "device_price_stars", None)
        else:
            included = 1
            effective_limit = subscription.max_devices
            max_purchasable = 0
            device_price_rub = 0
            device_price_stars = None

        can_renew = bool(plan is not None and getattr(plan, "price_rub", 0) > 0)

        return BotSubscriptionSummaryOut(
            id=subscription.id,
            plan_id=subscription.plan_id,
            plan_name=(plan.name if plan is not None else subscription.plan_name),
            status=self._classify_subscription(subscription),
            is_active=subscription.is_active,
            expires_at=subscription.expires_at,
            preferred_region=subscription.preferred_region,
            hwid_enabled=subscription.hwid_enabled,
            device_count=len(active_devices),
            device_limit=effective_limit,
            paid_device_slots=paid_slots,
            included_devices=included,
            max_purchasable_slots=max(max_purchasable, 0),
            device_price_rub=device_price_rub,
            device_price_stars=device_price_stars,
            can_renew=can_renew,
            used_traffic_bytes=subscription.used_traffic_bytes,
            lifetime_used_traffic_bytes=subscription.lifetime_used_traffic_bytes,
            traffic_limit_bytes=(plan.traffic_limit_bytes if plan is not None else None),
            last_traffic_reset_at=subscription.last_traffic_reset_at,
            last_payment_at=self._latest_paid_at(orders),
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )

    async def _current_subscription(self, user_id: UUID) -> SubscriptionOut | None:
        subscriptions = await self.subscription_service.list_subscriptions_by_user(
            user_id=user_id,
            active_only=False,
        )
        return self._pick_current_subscription(subscriptions)

    async def _list_orders(self, user_id: UUID) -> list[OrderOut]:
        rows, _ = await self.order_repository.list_by_user(user_id, limit=20, offset=0)
        return [OrderOut.model_validate(item) for item in rows]

    async def _build_service_status(self) -> BotServiceStatusOut:
        readiness = await self.admin_status_service.get_readiness()
        if readiness.ready:
            return BotServiceStatusOut(
                health=BotServiceHealth.OK,
                message="Сервис работает стабильно.",
            )
        failed = [item.detail for item in readiness.checks if not item.ok]
        return BotServiceStatusOut(
            health=BotServiceHealth.DEGRADED,
            message=failed[0] if failed else "Есть временная деградация сервиса.",
        )

    @staticmethod
    def _pick_current_subscription(
        subscriptions: Iterable[SubscriptionOut],
    ) -> SubscriptionOut | None:
        items = list(subscriptions)
        if not items:
            return None

        def sort_key(item: SubscriptionOut) -> tuple[int, datetime]:
            status = BotApiService._classify_subscription(item)
            priority = {
                BotDashboardState.ACTIVE: 4,
                BotDashboardState.EXPIRING: 3,
                BotDashboardState.EXPIRED: 2,
                BotDashboardState.INACTIVE: 1,
            }.get(status, 0)
            return priority, item.updated_at

        return max(items, key=sort_key)

    @staticmethod
    def _pick_pending_order(orders: Iterable[OrderOut]) -> OrderOut | None:
        now = datetime.now(timezone.utc)
        for order in orders:
            if order.status != "pending":
                continue
            if order.expires_at and order.expires_at < now:
                continue
            return order
        return None

    @staticmethod
    def _latest_paid_at(orders: Iterable[OrderOut]) -> datetime | None:
        for order in orders:
            if order.status in {"completed", "paid"}:
                return order.completed_at or order.paid_at or order.updated_at
        return None

    @staticmethod
    def _classify_subscription(subscription: SubscriptionOut) -> BotDashboardState:
        now = datetime.now(timezone.utc)
        if not subscription.is_active:
            return BotDashboardState.INACTIVE
        if subscription.expires_at and subscription.expires_at <= now:
            return BotDashboardState.EXPIRED
        if subscription.expires_at and subscription.expires_at <= now + timedelta(days=3):
            return BotDashboardState.EXPIRING
        return BotDashboardState.ACTIVE

    @staticmethod
    def _available_actions(
        *,
        state: BotDashboardState,
        subscription: BotSubscriptionSummaryOut | None,
        pending_order: OrderOut | None,
    ) -> list[BotAction]:
        actions: list[BotAction] = [BotAction.OPEN_HELP]
        if state in {BotDashboardState.NEW, BotDashboardState.NO_SUBSCRIPTION}:
            actions.extend([BotAction.CHOOSE_PLAN, BotAction.OPEN_PAYMENT])
            return actions
        if pending_order is not None and state == BotDashboardState.PENDING_PAYMENT:
            actions.extend([BotAction.CHECK_PAYMENT, BotAction.OPEN_PAYMENT])
            return actions
        if subscription is None:
            return actions
        if state in {BotDashboardState.ACTIVE, BotDashboardState.EXPIRING}:
            actions.extend(
                [
                    BotAction.OPEN_CONNECT,
                    BotAction.OPEN_DEVICES,
                    BotAction.ISSUE_LINK,
                    BotAction.RENEW,
                ]
            )
            if subscription is not None and subscription.max_purchasable_slots > 0:
                actions.append(BotAction.BUY_DEVICE_SLOTS)
            return actions
        actions.extend([BotAction.RENEW, BotAction.OPEN_PAYMENT])
        return actions

    @staticmethod
    def _to_bot_devices(devices: list[SubscriptionDeviceOut]) -> list[BotDeviceOut]:
        items: list[BotDeviceOut] = []
        for index, device in enumerate(devices, start=1):
            items.append(
                BotDeviceOut(
                    id=device.id,
                    display_name=BotApiService._device_name(device.user_agent, index),
                    hwid_hash=device.hwid_hash,
                    user_agent=device.user_agent,
                    last_seen_at=device.last_seen_at,
                    is_active=device.is_active,
                    created_at=device.created_at,
                    updated_at=device.updated_at,
                )
            )
        return items

    @staticmethod
    def _device_name(user_agent: str | None, index: int) -> str:
        if isinstance(user_agent, str):
            normalized = user_agent.strip()
            if normalized:
                return normalized[:80]
        return f"Устройство {index}"

    async def _encrypt_subscription_url_for_happ(self, subscription_url: str) -> str:
        api_url = self.settings.subscriptions.happ_crypto_api_url.strip()
        if not api_url or not subscription_url:
            return subscription_url

        timeout = max(1.0, float(self.settings.subscriptions.happ_crypto_timeout_sec))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    api_url,
                    json={"url": subscription_url},
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
            return self._parse_happ_crypto_response(response)
        except Exception:
            log.exception("happ_link_encryption_failed")
            return subscription_url

    @classmethod
    def _parse_happ_crypto_response(cls, response: httpx.Response) -> str:
        text = response.text.strip()
        if not text:
            raise ValueError("Happ crypto API returned empty body")

        value = text
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type or text[:1] in {"{", "["}:
            try:
                value = cls._extract_happ_crypto_url(response.json())
            except Exception:
                value = text

        value = value.strip()
        if not value.startswith("happ://crypt5/"):
            raise ValueError(f"Unexpected Happ crypto payload: {value[:64]}")
        return value

    @classmethod
    def _extract_happ_crypto_url(cls, payload) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            for key in ("url", "encrypted_url", "encryptedUrl", "result", "data", "link"):
                value = payload.get(key)
                if value:
                    return cls._extract_happ_crypto_url(value)
        if isinstance(payload, list):
            for item in payload:
                value = cls._extract_happ_crypto_url(item)
                if value:
                    return value
        raise ValueError("Unable to extract Happ crypto URL")


def get_bot_api_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> BotApiService:
    return BotApiService(session, redis)
