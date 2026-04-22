from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProbePolicyOut(BaseModel):
    id: UUID
    route_suspected_after_failures: int
    route_degraded_after_failures: int
    route_block_after_failures: int
    route_block_cooldown_hours: int
    auto_drain_enabled: bool
    auto_drain_tick_sec: int
    auto_drain_min_consecutive_failures: int
    auto_drain_max_probe_age_sec: int
    auto_drain_max_nodes: int
    auto_undrain_enabled: bool
    auto_undrain_min_consecutive_successes: int
    auto_undrain_max_probe_age_sec: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProbePolicyUpdateIn(BaseModel):
    route_suspected_after_failures: int | None = Field(default=None, ge=1, le=50)
    route_degraded_after_failures: int | None = Field(default=None, ge=2, le=50)
    route_block_after_failures: int | None = Field(default=None, ge=3, le=50)
    route_block_cooldown_hours: int | None = Field(default=None, ge=1, le=168)
    auto_drain_enabled: bool | None = None
    auto_drain_tick_sec: int | None = Field(default=None, ge=30, le=3600)
    auto_drain_min_consecutive_failures: int | None = Field(default=None, ge=1, le=50)
    auto_drain_max_probe_age_sec: int | None = Field(default=None, ge=60, le=86400)
    auto_drain_max_nodes: int | None = Field(default=None, ge=1, le=500)
    auto_undrain_enabled: bool | None = None
    auto_undrain_min_consecutive_successes: int | None = Field(default=None, ge=1, le=50)
    auto_undrain_max_probe_age_sec: int | None = Field(default=None, ge=60, le=86400)

    model_config = ConfigDict(extra="forbid")
