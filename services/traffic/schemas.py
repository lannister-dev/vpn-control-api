from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserTrafficIn(BaseModel):
    identifier: str = Field(min_length=1)
    uplink_bytes: int = Field(default=0, ge=0)
    downlink_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    node_id: str | None = Field(default=None, description="Source node identifier for per-node delta tracking")

    model_config = ConfigDict(extra="ignore")


class TrafficUsageCreate(BaseModel):
    key_id: UUID
    delta_bytes: int = Field(ge=0)
    reported_total_bytes: int = Field(ge=0)


class TrafficKeySummaryOut(BaseModel):
    id: UUID
    user_id: UUID
    client_id: str
    protocol: str
    transport: str
    valid_until: datetime
    traffic_limit_mb: int
    used_traffic_bytes: int
    last_reported_total_bytes: int
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


class KeyNodeTrafficCounterCreate(BaseModel):
    key_id: UUID
    node_id: str
    last_reported_total_bytes: int
