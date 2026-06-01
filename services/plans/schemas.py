from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResetStrategy(str, Enum):
    NO_RESET = "NO_RESET"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"


class PlanPeriodIn(BaseModel):
    months: int = Field(ge=1, le=36)
    price_rub: Decimal = Field(ge=0)
    price_stars: int | None = Field(default=None, ge=1)


class PlanPeriodOut(BaseModel):
    months: int
    price_rub: Decimal
    price_stars: int | None = None
    savings_pct: int | None = None

    model_config = ConfigDict(from_attributes=True)


def _compute_savings(periods: list[PlanPeriodOut]) -> list[PlanPeriodOut]:
    monthly = next((p.price_rub for p in periods if p.months == 1), None)
    if not monthly or monthly <= 0:
        return periods
    for period in periods:
        if period.months <= 1:
            continue
        baseline = monthly * period.months
        if baseline <= 0:
            continue
        pct = round((1 - period.price_rub / baseline) * 100)
        period.savings_pct = pct if pct > 0 else None
    return periods


class PlanCreateIn(BaseModel):
    name: str = Field(max_length=64)
    description: str | None = None
    traffic_limit_bytes: int = Field(default=0, ge=0)  # 0 = unlimited
    reset_strategy: ResetStrategy = ResetStrategy.NO_RESET
    max_devices: int = Field(default=5, ge=1, le=100)
    included_devices: int = Field(default=1, ge=1, le=100)
    duration_days: int = Field(default=30, ge=1, le=3650)
    sort_order: int = Field(default=0, ge=0)
    whitelist_enabled: bool = False
    entry_relay_enabled: bool = False
    price_rub: Decimal = Field(default=Decimal("0"), ge=0)
    device_price_rub: Decimal = Field(default=Decimal("0"), ge=0)
    price_stars: int | None = Field(default=None, ge=1)
    device_price_stars: int | None = Field(default=None, ge=1)
    periods: list[PlanPeriodIn] | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _included_le_max(self):
        if self.included_devices > self.max_devices:
            raise ValueError("included_devices must be <= max_devices")
        return self

    @model_validator(mode="after")
    def _unique_periods(self):
        if self.periods:
            seen = [p.months for p in self.periods]
            if len(seen) != len(set(seen)):
                raise ValueError("period months must be unique")
        return self


class PlanUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = None
    traffic_limit_bytes: int | None = Field(default=None, ge=0)
    reset_strategy: ResetStrategy | None = None
    max_devices: int | None = Field(default=None, ge=1, le=100)
    included_devices: int | None = Field(default=None, ge=1, le=100)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    whitelist_enabled: bool | None = None
    entry_relay_enabled: bool | None = None
    price_rub: Decimal | None = Field(default=None, ge=0)
    device_price_rub: Decimal | None = Field(default=None, ge=0)
    price_stars: int | None = Field(default=None, ge=1)
    device_price_stars: int | None = Field(default=None, ge=1)
    periods: list[PlanPeriodIn] | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _unique_periods(self):
        if self.periods:
            seen = [p.months for p in self.periods]
            if len(seen) != len(set(seen)):
                raise ValueError("period months must be unique")
        return self


class PlanOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    traffic_limit_bytes: int
    reset_strategy: str
    max_devices: int
    included_devices: int
    duration_days: int
    sort_order: int
    whitelist_enabled: bool
    entry_relay_enabled: bool
    price_rub: Decimal
    device_price_rub: Decimal
    price_stars: int | None
    device_price_stars: int | None
    periods: list[PlanPeriodOut] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _fill_savings(self):
        _compute_savings(self.periods)
        return self


class PlanListOut(BaseModel):
    items: list[PlanOut]
    total: int
