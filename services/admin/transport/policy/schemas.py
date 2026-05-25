from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransportPolicyOut(BaseModel):
    id: UUID
    cleanup_enabled: bool
    cleanup_tick_sec: int
    retention_days: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransportPolicyUpdateIn(BaseModel):
    cleanup_enabled: bool | None = None
    cleanup_tick_sec: int | None = Field(default=None, ge=60, le=86400)
    retention_days: int | None = Field(default=None, ge=1, le=365)

    model_config = ConfigDict(extra="forbid")
