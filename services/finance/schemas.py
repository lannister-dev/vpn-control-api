from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExpenseKindEnum(str, Enum):
    INFRASTRUCTURE = "infrastructure"
    GATEWAY_FEE = "gateway_fee"
    DOMAIN_CDN = "domain_cdn"
    MARKETING = "marketing"
    SALARY = "salary"
    REFERRAL = "referral"
    TAX = "tax"
    OTHER = "other"


class RecurringPeriodEnum(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class _FxValidatedIn(BaseModel):
    @model_validator(mode="after")
    def _check_fx(self):
        currency = (self.currency or "RUB").upper()
        if currency != "RUB" and (self.fx_rate is None or self.fx_rate <= 0):
            raise ValueError("fx_rate is required and must be > 0 for non-RUB currency")
        return self


class ExpenseCreateIn(_FxValidatedIn):
    kind: ExpenseKindEnum
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    incurred_at: datetime
    period_start: datetime | None = None
    period_end: datetime | None = None
    vendor: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=256)


class ExpenseUpdateIn(BaseModel):
    kind: ExpenseKindEnum | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    incurred_at: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    vendor: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=256)


class ExpenseOut(BaseModel):
    id: UUID
    kind: str
    amount: Decimal
    currency: str
    amount_rub: Decimal
    fx_rate: Decimal | None
    incurred_at: datetime
    period_start: datetime | None
    period_end: datetime | None
    vendor: str | None
    region: str | None
    description: str | None
    template_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseListOut(BaseModel):
    items: list[ExpenseOut]
    total: int


class ExpenseKindSummaryOut(BaseModel):
    kind: str
    total_rub: Decimal
    count: int


class ExpenseSummaryOut(BaseModel):
    items: list[ExpenseKindSummaryOut]
    total_rub: Decimal


class RecurringTemplateCreateIn(_FxValidatedIn):
    name: str = Field(min_length=1, max_length=128)
    kind: ExpenseKindEnum
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    period: RecurringPeriodEnum
    next_run_at: datetime
    vendor: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=256)


class RecurringTemplateUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    kind: ExpenseKindEnum | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    period: RecurringPeriodEnum | None = None
    next_run_at: datetime | None = None
    vendor: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=256)
    is_active: bool | None = None


class RecurringTemplateOut(BaseModel):
    id: UUID
    name: str
    kind: str
    amount: Decimal
    currency: str
    fx_rate: Decimal | None
    period: str
    next_run_at: datetime
    vendor: str | None
    region: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecurringTemplateListOut(BaseModel):
    items: list[RecurringTemplateOut]


# ── Analytics (Overview / Income) ─────────────────────────────

class KpiOut(BaseModel):
    value: float
    delta_pct: float | None = None
    tone: str = "flat"


class DailyPointOut(BaseModel):
    date: str
    income: float
    commissions: float
    expense: float
    profit: float


class WaterfallItemOut(BaseModel):
    key: str
    type: str
    value: float


class OverviewOut(BaseModel):
    gross: KpiOut
    commissions: KpiOut
    net: KpiOut
    expenses: KpiOut
    profit: KpiOut
    margin: KpiOut
    daily: list[DailyPointOut]
    waterfall: list[WaterfallItemOut]


class BreakdownItemOut(BaseModel):
    key: str
    value: float


class IncomeTxnOut(BaseModel):
    id: UUID
    paid_at: datetime | None
    user: str | None
    provider: str
    order_type: str
    period_months: int
    amount_rub: Decimal
    fee_rub: Decimal | None
    net_rub: Decimal | None
    status: str
    is_top_up: bool


class IncomeOut(BaseModel):
    by_provider: list[BreakdownItemOut]
    by_order_type: list[BreakdownItemOut]
    by_period: list[BreakdownItemOut]
    topup_volume: float
    uncaptured_pct: float
    transactions: list[IncomeTxnOut]


class MrrPointOut(BaseModel):
    month: str
    base: float
    neu: float
    exp: float
    chu: float


class MetricsOut(BaseModel):
    mrr: float
    arr: float
    arpu: float
    paying_users: int
    new_paying_users: int
    churn_rate: float
    ltv: float
    cac: float
    ltv_cac: float | None
    acquisition_cost: float
    mrr_series: list[MrrPointOut]
