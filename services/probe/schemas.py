from datetime import datetime
import json
from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ProbeDetailsValue: TypeAlias = str | int | float | bool | None
ProbeDetails: TypeAlias = dict[str, ProbeDetailsValue]


class ProbeReportIn(BaseModel):
    node_id: UUID
    source: str = Field(min_length=1, max_length=64)
    is_reachable: bool
    latency_ms: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=255)
    checked_at: datetime | None = None
    details: ProbeDetails = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: ProbeDetails) -> ProbeDetails:
        if len(value) > 32:
            raise ValueError("details must contain at most 32 keys")
        for key, item in value.items():
            if len(key) > 64:
                raise ValueError("details keys must be <= 64 chars")
            if isinstance(item, str) and len(item) > 256:
                raise ValueError("details string values must be <= 256 chars")
        serialized = json.dumps(value, ensure_ascii=False)
        if len(serialized) > 4096:
            raise ValueError("details payload is too large")
        return value


class ProbeReportOut(BaseModel):
    id: UUID
    node_id: UUID
    source: str
    is_reachable: bool
    latency_ms: int | None
    error: str | None
    checked_at: datetime
    details: ProbeDetails
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProbeSignalInternalCreate(BaseModel):
    node_id: UUID
    source: str = Field(min_length=1, max_length=64)
    is_reachable: bool
    latency_ms: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=255)
    checked_at: datetime
    details: ProbeDetails = Field(default_factory=dict)


class ProbeTargetOut(BaseModel):
    node_id: UUID
    node_name: str
    role: str
    region: str
    host: str
    port: int


class ProbeDrainMigrateIn(BaseModel):
    source_backend_id: UUID
    target_backend_id: UUID | None = None
    require_recent_failure: bool = True
    max_probe_age_sec: int = Field(default=600, ge=30, le=86400)
    min_consecutive_failures: int = Field(default=1, ge=1, le=10)
    source: str | None = Field(default=None, max_length=64)
    last_migration_reason: str = Field(default="probe_failure", max_length=64)


class ProbeDrainMigrateOut(BaseModel):
    source_backend_id: UUID
    target_backend_id: UUID
    migrated_count: int
    drained: bool
    probe_report_id: UUID | None = None


class ProbeAutoDrainMigrateIn(BaseModel):
    backend_node_ids: list[UUID] | None = None
    target_backend_id: UUID | None = None
    source: str | None = Field(default=None, max_length=64)
    require_recent_failure: bool = True
    max_probe_age_sec: int = Field(default=600, ge=30, le=86400)
    min_consecutive_failures: int = Field(default=1, ge=1, le=10)
    include_already_draining: bool = False
    dry_run: bool = False
    max_nodes: int = Field(default=20, ge=1, le=200)
    last_migration_reason: str = Field(default="probe_auto_failure", max_length=64)


class ProbeAutoDrainMigrateItemOut(BaseModel):
    source_backend_id: UUID | None = None
    action: Literal["migrated", "would_migrate", "skipped", "error"]
    detail: str | None = None
    target_backend_id: UUID | None = None
    migrated_count: int = 0
    probe_report_id: UUID | None = None


class ProbeAutoDrainMigrateOut(BaseModel):
    processed: int
    migrated: int
    skipped: int
    dry_run: bool
    items: list[ProbeAutoDrainMigrateItemOut]


class ProbeCleanupOut(BaseModel):
    deleted: int = Field(ge=0)
    retention_days: int = Field(ge=1)
