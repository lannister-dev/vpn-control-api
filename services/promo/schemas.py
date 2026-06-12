from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiscountType(str, Enum):
    PERCENT = "percent"
    FIXED = "fixed"


class PromoAudience(str, Enum):
    ALL = "all"
    NO_SUBSCRIPTION = "no_subscription"
    HAS_SUBSCRIPTION = "has_subscription"
    BY_PLAN = "by_plan"


class PromoAppliesTo(str, Enum):
    ANY = "any"
    NEW_PURCHASE = "new_purchase"
    RENEWAL = "renewal"


class PromoCodeCreateIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=256)
    discount_type: DiscountType
    discount_value: Decimal = Field(gt=0)
    max_discount_rub: Decimal | None = Field(default=None, gt=0)
    audience: PromoAudience = PromoAudience.ALL
    plan_ids: list[UUID] | None = None
    applies_to: PromoAppliesTo = PromoAppliesTo.ANY
    min_amount_rub: Decimal | None = Field(default=None, ge=0)
    max_activations: int | None = Field(default=None, gt=0)
    max_per_user: int = Field(default=1, gt=0)
    starts_at: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.discount_type == DiscountType.PERCENT and self.discount_value > 100:
            raise ValueError("percent discount must be <= 100")
        if self.audience == PromoAudience.BY_PLAN and not self.plan_ids:
            raise ValueError("plan_ids required for audience=by_plan")
        return self


class PromoCodeUpdateIn(BaseModel):
    description: str | None = Field(default=None, max_length=256)
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, gt=0)
    max_discount_rub: Decimal | None = Field(default=None, gt=0)
    audience: PromoAudience | None = None
    plan_ids: list[UUID] | None = None
    applies_to: PromoAppliesTo | None = None
    min_amount_rub: Decimal | None = Field(default=None, ge=0)
    max_activations: int | None = Field(default=None, gt=0)
    max_per_user: int | None = Field(default=None, gt=0)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool | None = None


class PromoCodeOut(BaseModel):
    id: UUID
    code: str
    description: str | None
    discount_type: str
    discount_value: Decimal
    max_discount_rub: Decimal | None
    audience: str
    plan_ids: list[UUID] | None
    applies_to: str
    min_amount_rub: Decimal | None
    max_activations: int | None
    max_per_user: int
    starts_at: datetime | None
    expires_at: datetime | None
    activation_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromoCodeListOut(BaseModel):
    items: list[PromoCodeOut]


class PromoValidateIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    user_id: UUID
    plan_id: UUID | None = None
    order_type: str = "plan_purchase"
    amount_rub: Decimal = Field(gt=0)


class PromoQuoteOut(BaseModel):
    code: str
    promo_code_id: UUID
    amount_before: Decimal
    discount_rub: Decimal
    amount_after: Decimal


class PromoActivationOut(BaseModel):
    id: UUID
    user_id: UUID
    order_id: UUID | None
    amount_before: Decimal
    discount_applied: Decimal
    amount_after: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromoActivationListOut(BaseModel):
    items: list[PromoActivationOut]
    total: int


class PromoStatsOut(BaseModel):
    promo_code_id: UUID
    activations: int
    unique_users: int
    total_discount_rub: Decimal
    revenue_after_rub: Decimal
