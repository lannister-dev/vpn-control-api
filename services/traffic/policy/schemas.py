from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TrafficPolicyOut(BaseModel):
    id: UUID
    user_cleanup_enabled: bool
    user_cleanup_tick_sec: int
    user_retention_days: int
    node_cleanup_enabled: bool
    node_cleanup_tick_sec: int
    node_retention_days: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrafficPolicyUpdateIn(BaseModel):
    user_cleanup_enabled: bool | None = None
    user_cleanup_tick_sec: int | None = Field(default=None, ge=60, le=86400)
    user_retention_days: int | None = Field(default=None, ge=1, le=365)
    node_cleanup_enabled: bool | None = None
    node_cleanup_tick_sec: int | None = Field(default=None, ge=60, le=86400)
    node_retention_days: int | None = Field(default=None, ge=1, le=365)

    model_config = ConfigDict(extra="forbid")
