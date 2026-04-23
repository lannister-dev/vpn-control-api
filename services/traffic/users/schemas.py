from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserTrafficIn(BaseModel):
    identifier: str = Field(min_length=1)
    delta_bytes: int = Field(ge=0)

    model_config = ConfigDict(extra="ignore")


class TrafficUsageCreate(BaseModel):
    key_id: UUID
    delta_bytes: int = Field(ge=0)
    reported_total_bytes: int = Field(default=0, ge=0)


class TrafficKeySummaryOut(BaseModel):
    id: UUID
    user_id: UUID
    client_id: str
    protocol: str
    transport: str
    valid_until: datetime
    traffic_limit_mb: int
    used_traffic_bytes: int
    is_revoked: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrafficKeySummaryListOut(BaseModel):
    items: list[TrafficKeySummaryOut]
    total: int
    limit: int
    offset: int


class TrafficHistoryItemOut(BaseModel):
    id: UUID
    key_id: UUID
    delta_bytes: int
    reported_total_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrafficHistoryListOut(BaseModel):
    items: list[TrafficHistoryItemOut]
    total: int
    limit: int
    offset: int


class UserTrafficSummaryOut(BaseModel):
    user_id: UUID
    telegram_id: int | None = None
    username: str | None = None
    plan_name: str | None = None
    bytes: int
    keys: int


class UserTrafficSummaryListOut(BaseModel):
    period: str
    from_ts: datetime
    to_ts: datetime
    items: list[UserTrafficSummaryOut]
