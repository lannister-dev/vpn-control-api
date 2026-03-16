from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlacementDesiredState(str, Enum):
    active = "active"
    inactive = "inactive"


class PlacementAppliedState(str, Enum):
    pending = "pending"
    applied = "applied"
    error = "error"


class UserPlacementUpsertIn(BaseModel):
    key_id: UUID
    backend_node_id: UUID
    desired_state: PlacementDesiredState = PlacementDesiredState.active
    sticky_until: datetime | None = None
    last_migration_reason: str | None = Field(default=None, max_length=64)


class PlacementMigrateBackendIn(BaseModel):
    source_backend_id: UUID
    target_backend_id: UUID | None = None
    last_migration_reason: str = Field(default="admin_manual", max_length=64)


class PlacementMigrateBackendOut(BaseModel):
    source_backend_id: UUID
    target_backend_id: UUID
    migrated_count: int


class UserPlacementOut(BaseModel):
    id: UUID
    key_id: UUID
    backend_node_id: UUID
    desired_state: PlacementDesiredState
    applied_state: PlacementAppliedState
    op_version: int
    applied_version: int
    sticky_until: datetime | None
    last_migration_reason: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlacementApplyResultIn(BaseModel):
    op_version: int = Field(ge=1)
    applied_state: PlacementAppliedState


PlacementApplyStatus = Literal[
    "applied",
    "pending",
    "error",
    "skipped_stale",
    "skipped_idempotent",
]


class PlacementUpdate(BaseModel):
    applied_state: PlacementAppliedState
    applied_version: int = Field(ge=0)
    updated_at: datetime


class PlacementBackendMigrationUpdate(BaseModel):
    backend_node_id: UUID
    applied_state: PlacementAppliedState
    op_version: int = Field(ge=1)
    last_migration_reason: str | None = Field(default=None, max_length=64)
    updated_at: datetime
