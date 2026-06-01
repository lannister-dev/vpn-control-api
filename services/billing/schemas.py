from datetime import datetime
from decimal import Decimal
from enum import Enum, IntEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.billing.utils import validate_provider_payment_method


class PaymentProviderEnum(str, Enum):
    CRYPTO = "crypto"
    FREEKASSA = "freekassa"
    STARS = "stars"
    PLATEGA = "platega"
    BALANCE = "balance"
    FREE = "free"


class PlategaPaymentMethodEnum(IntEnum):
    SBP_QR = 2
    ERIP = 3
    CARD_ACQUIRING = 11
    INTERNATIONAL = 12
    CRYPTO = 13


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    COMPLETED = "completed"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class TransactionType(str, Enum):
    PAYMENT = "payment"
    PURCHASE = "purchase"
    MANUAL_CREDIT = "manual_credit"
    REFUND = "refund"
    DEVICE_SLOT_PURCHASE = "device_slot_purchase"


class OrderTypeEnum(str, Enum):
    PLAN_PURCHASE = "plan_purchase"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    DEVICE_SLOTS = "device_slots"
    TOP_UP = "top_up"


# ── Order I/O ─────────────────────────────────────────────────

class OrderCreateIn(BaseModel):
    user_id: UUID
    plan_id: UUID | None = None
    amount_rub: Decimal | None = None
    provider: PaymentProviderEnum
    order_type: OrderTypeEnum = OrderTypeEnum.PLAN_PURCHASE
    device_slots_qty: int = 0
    period_months: int = 1
    subscription_id: UUID | None = None
    payment_method: PlategaPaymentMethodEnum | None = None

    @model_validator(mode="after")
    def validate_provider_requirements(self) -> "OrderCreateIn":
        validate_provider_payment_method(
            self.provider,
            payment_method=self.payment_method,
        )
        return self

    @model_validator(mode="after")
    def validate_period(self) -> "OrderCreateIn":
        from services.billing.constants import ALLOWED_PERIOD_MONTHS

        if self.period_months not in ALLOWED_PERIOD_MONTHS:
            raise ValueError(f"period_months must be one of {ALLOWED_PERIOD_MONTHS}")
        return self


class OrderInternalCreate(BaseModel):
    user_id: UUID
    plan_id: UUID | None = None
    amount_rub: Decimal
    provider: str
    status: str = OrderStatus.PENDING
    external_id: str
    payment_url: str | None = None
    provider_meta: str | None = None
    expires_at: datetime | None = None
    subscription_id: UUID | None = None
    order_type: str = "plan_purchase"
    device_slots_qty: int = 0
    period_months: int = 1


class OrderInternalUpdate(BaseModel):
    status: str | None = None
    paid_at: datetime | None = None
    completed_at: datetime | None = None
    provider_meta: str | None = None
    subscription_id: UUID | None = None

    model_config = ConfigDict(exclude_none=True)


class TransactionInternalCreate(BaseModel):
    user_id: UUID
    amount: Decimal
    balance_after: Decimal
    type: str
    order_id: UUID | None = None
    description: str | None = None


class OrderOut(BaseModel):
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
    period_months: int = 1
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderListOut(BaseModel):
    items: list[OrderOut]
    total: int


class OrderPreviewOut(BaseModel):
    plan_id: UUID
    period_months: int
    period_price: Decimal
    proration_credit: Decimal = Decimal("0")
    amount_due: Decimal
    is_switch: bool = False


class OrderRefundIn(BaseModel):
    reason: str = Field(min_length=1, max_length=512)
    deactivate_subscription: bool = True


# ── Balance I/O ───────────────────────────────────────────────

class BalanceCreditIn(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("99999999.99"))
    description: str | None = Field(default=None, max_length=256)


class BalanceOut(BaseModel):
    user_id: UUID
    balance: Decimal


class TransactionOut(BaseModel):
    id: UUID
    user_id: UUID
    amount: Decimal
    balance_after: Decimal
    type: str
    order_id: UUID | None
    description: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
