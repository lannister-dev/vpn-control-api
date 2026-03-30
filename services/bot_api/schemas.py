from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.billing.schemas import PaymentProviderEnum


class BotDashboardState(str, Enum):
    NEW = "new"
    NO_SUBSCRIPTION = "no_subscription"
    PENDING_PAYMENT = "pending_payment"
    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    INACTIVE = "inactive"


class BotServiceHealth(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"


class BotAction(str, Enum):
    CHOOSE_PLAN = "choose_plan"
    OPEN_CONNECT = "open_connect"
    OPEN_DEVICES = "open_devices"
    OPEN_PAYMENT = "open_payment"
    ISSUE_LINK = "issue_link"
    RENEW = "renew"
    CHECK_PAYMENT = "check_payment"
    OPEN_HELP = "open_help"
    BUY_DEVICE_SLOTS = "buy_device_slots"


class BotSessionSyncIn(BaseModel):
    telegram_id: int
    username: str | None = Field(default=None, max_length=128)
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)


class BotOrderCreateIn(BaseModel):
    plan_id: UUID
    provider: PaymentProviderEnum
    extra_devices: int = Field(default=0, ge=0)


class BotStarsConfirmIn(BaseModel):
    telegram_payment_charge_id: str = Field(max_length=256)
    total_amount: int = Field(ge=1)


class BotRenewOrderIn(BaseModel):
    provider: PaymentProviderEnum


class BotTopUpCreateIn(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("99999999.99"))
    provider: PaymentProviderEnum


class BotUserOut(BaseModel):
    id: UUID
    telegram_id: int
    username: str | None
    balance: Decimal
    is_active: bool
    tag: str | None = None
    description: str | None = None
    terms_accepted: bool = False
    terms_accepted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BotServiceStatusOut(BaseModel):
    health: BotServiceHealth
    message: str


class BotPlanOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    traffic_limit_bytes: int
    reset_strategy: str
    max_devices: int
    included_devices: int = 1
    duration_days: int
    sort_order: int
    whitelist_enabled: bool
    price_rub: Decimal
    device_price_rub: Decimal = Decimal("0")
    price_stars: int | None = None
    device_price_stars: int | None = None
    is_active: bool
    is_current: bool = False
    can_renew: bool = True
    created_at: datetime
    updated_at: datetime


class BotPlanListOut(BaseModel):
    items: list[BotPlanOut]
    total: int
    current_plan_id: UUID | None = None
    used_trial_plan_ids: list[UUID] = []


class BotOrderOut(BaseModel):
    id: UUID
    user_id: UUID
    plan_id: UUID | None
    amount_rub: Decimal
    provider: str
    status: str
    external_id: str
    payment_url: str | None
    paid_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    subscription_id: UUID | None
    order_type: str = "plan_purchase"
    device_slots_qty: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BotSubscriptionSummaryOut(BaseModel):
    id: UUID
    plan_id: UUID | None = None
    plan_name: str | None = None
    status: BotDashboardState
    is_active: bool
    expires_at: datetime | None = None
    preferred_region: str | None = None
    hwid_enabled: bool
    device_count: int = 0
    device_limit: int | None = None
    paid_device_slots: int = 0
    included_devices: int = 1
    max_purchasable_slots: int = 0
    device_price_rub: Decimal = Decimal("0")
    device_price_stars: int | None = None
    can_renew: bool = True
    used_traffic_bytes: int = 0
    lifetime_used_traffic_bytes: int = 0
    traffic_limit_bytes: int | None = None
    last_traffic_reset_at: datetime | None = None
    last_payment_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BotSessionOut(BaseModel):
    user: BotUserOut
    state: BotDashboardState
    is_new_user: bool = False
    subscription: BotSubscriptionSummaryOut | None = None
    pending_order: BotOrderOut | None = None
    service: BotServiceStatusOut
    available_actions: list[BotAction]


class BotOrderActionOut(BaseModel):
    order: BotOrderOut
    session: BotSessionOut


class BotRenewOfferOut(BaseModel):
    subscription_id: UUID
    plan_id: UUID
    plan_name: str
    status: BotDashboardState
    duration_days: int
    price_rub: Decimal
    price_stars: int | None = None
    current_expires_at: datetime | None = None
    renewed_expires_at: datetime
    providers: list[PaymentProviderEnum] = Field(default_factory=list)
    is_reactivation: bool = False


class BotDeviceOut(BaseModel):
    id: UUID
    display_name: str
    hwid_hash: str
    user_agent: str | None = None
    last_seen_at: datetime | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BotDevicesOut(BaseModel):
    session: BotSessionOut
    items: list[BotDeviceOut]
    total: int
    active_total: int


class BotSubscriptionLinkOut(BaseModel):
    subscription_url: str
    session: BotSessionOut


class BotDeviceSlotPurchaseIn(BaseModel):
    qty: int = Field(ge=1)
    provider: PaymentProviderEnum


class BotOrderHistoryItemOut(BaseModel):
    id: UUID
    plan_name: str | None = None
    amount_rub: Decimal
    provider: str
    status: str
    order_type: str = "plan_purchase"
    device_slots_qty: int = 0
    paid_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class BotOrderHistoryOut(BaseModel):
    items: list[BotOrderHistoryItemOut]
    total: int
