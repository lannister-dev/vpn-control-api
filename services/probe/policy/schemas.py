from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProbePolicyOut(BaseModel):
    id: UUID

    auto_route_health_enabled: bool

    route_suspected_after_failures: int
    route_degraded_after_failures: int
    route_block_after_failures: int
    route_block_cooldown_hours: int

    auto_drain_enabled: bool
    auto_drain_tick_sec: int
    auto_drain_min_consecutive_failures: int
    auto_drain_max_probe_age_sec: int
    auto_drain_max_nodes: int
    auto_drain_source: str | None = None
    auto_drain_require_recent_failure: bool
    auto_drain_include_already_draining: bool
    auto_drain_target_backend_id: UUID | None = None
    auto_drain_last_migration_reason: str

    auto_undrain_enabled: bool
    auto_undrain_min_consecutive_successes: int
    auto_undrain_max_probe_age_sec: int
    auto_undrain_source: str | None = None

    retention_days: int
    cleanup_enabled: bool
    cleanup_tick_sec: int

    synthetic_reconcile_enabled: bool
    synthetic_reconcile_tick_sec: int
    synthetic_key_valid_days: int
    synthetic_key_traffic_limit_mb: int

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProbePolicyUpdateIn(BaseModel):
    auto_route_health_enabled: bool | None = None

    route_suspected_after_failures: int | None = Field(default=None, ge=1, le=50)
    route_degraded_after_failures: int | None = Field(default=None, ge=2, le=50)
    route_block_after_failures: int | None = Field(default=None, ge=3, le=50)
    route_block_cooldown_hours: int | None = Field(default=None, ge=1, le=168)

    auto_drain_enabled: bool | None = None
    auto_drain_tick_sec: int | None = Field(default=None, ge=30, le=3600)
    auto_drain_min_consecutive_failures: int | None = Field(default=None, ge=1, le=50)
    auto_drain_max_probe_age_sec: int | None = Field(default=None, ge=60, le=86400)
    auto_drain_max_nodes: int | None = Field(default=None, ge=1, le=500)
    auto_drain_source: str | None = Field(default=None, max_length=64)
    auto_drain_require_recent_failure: bool | None = None
    auto_drain_include_already_draining: bool | None = None
    auto_drain_target_backend_id: UUID | None = None
    auto_drain_last_migration_reason: str | None = Field(default=None, max_length=64)

    auto_undrain_enabled: bool | None = None
    auto_undrain_min_consecutive_successes: int | None = Field(default=None, ge=1, le=50)
    auto_undrain_max_probe_age_sec: int | None = Field(default=None, ge=60, le=86400)
    auto_undrain_source: str | None = Field(default=None, max_length=64)

    retention_days: int | None = Field(default=None, ge=1, le=365)
    cleanup_enabled: bool | None = None
    cleanup_tick_sec: int | None = Field(default=None, ge=60, le=86400)

    synthetic_reconcile_enabled: bool | None = None
    synthetic_reconcile_tick_sec: int | None = Field(default=None, ge=30, le=86400)
    synthetic_key_valid_days: int | None = Field(default=None, ge=1, le=36500)
    synthetic_key_traffic_limit_mb: int | None = Field(default=None, ge=1, le=10_485_760)

    model_config = ConfigDict(extra="forbid")
