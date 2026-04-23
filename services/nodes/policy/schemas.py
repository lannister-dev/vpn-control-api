from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NodePolicyOut(BaseModel):
    id: UUID

    stale_after_sec: int
    heartbeat_unhealthy_drain_threshold: int
    heartbeat_healthy_undrain_threshold: int

    auto_heal_enabled: bool
    auto_heal_tick_sec: int
    auto_heal_max_nodes: int
    auto_heal_drain_cooldown_sec: int
    auto_undrain_enabled: bool

    placement_error_retry_enabled: bool
    placement_error_retry_tick_sec: int
    placement_error_retry_after_sec: int

    placement_rebalance_enabled: bool
    placement_rebalance_tick_sec: int
    placement_rebalance_batch_size: int

    entry_apply_fail_threshold: int
    entry_apply_fail_unhealthy: bool
    entry_auto_drain_enabled: bool
    entry_auto_drain_tick_sec: int
    entry_auto_drain_probe_failures: int
    entry_auto_drain_max_nodes: int
    entry_auto_drain_reason: str
    entry_auto_undrain_enabled: bool
    entry_auto_undrain_healthy_ticks: int

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NodePolicyUpdateIn(BaseModel):
    stale_after_sec: int | None = Field(default=None, ge=30, le=3600)
    heartbeat_unhealthy_drain_threshold: int | None = Field(default=None, ge=1, le=50)
    heartbeat_healthy_undrain_threshold: int | None = Field(default=None, ge=1, le=50)

    auto_heal_enabled: bool | None = None
    auto_heal_tick_sec: int | None = Field(default=None, ge=30, le=3600)
    auto_heal_max_nodes: int | None = Field(default=None, ge=1, le=500)
    auto_heal_drain_cooldown_sec: int | None = Field(default=None, ge=0, le=86400)
    auto_undrain_enabled: bool | None = None

    placement_error_retry_enabled: bool | None = None
    placement_error_retry_tick_sec: int | None = Field(default=None, ge=30, le=3600)
    placement_error_retry_after_sec: int | None = Field(default=None, ge=30, le=86400)

    placement_rebalance_enabled: bool | None = None
    placement_rebalance_tick_sec: int | None = Field(default=None, ge=30, le=3600)
    placement_rebalance_batch_size: int | None = Field(default=None, ge=1, le=10000)

    entry_apply_fail_threshold: int | None = Field(default=None, ge=1, le=50)
    entry_apply_fail_unhealthy: bool | None = None
    entry_auto_drain_enabled: bool | None = None
    entry_auto_drain_tick_sec: int | None = Field(default=None, ge=15, le=3600)
    entry_auto_drain_probe_failures: int | None = Field(default=None, ge=1, le=50)
    entry_auto_drain_max_nodes: int | None = Field(default=None, ge=1, le=500)
    entry_auto_drain_reason: str | None = Field(default=None, max_length=64)
    entry_auto_undrain_enabled: bool | None = None
    entry_auto_undrain_healthy_ticks: int | None = Field(default=None, ge=1, le=50)

    model_config = ConfigDict(extra="forbid")
