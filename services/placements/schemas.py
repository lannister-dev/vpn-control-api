from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from services.vpn.keys.schemas import VpnProtocol, VpnTransport


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


class PlacementReportIn(BaseModel):
    op_version: int = Field(ge=1)
    applied_state: PlacementAppliedState


PlacementReportStatus = Literal[
    "applied",
    "pending",
    "error",
    "skipped_stale",
    "skipped_idempotent",
]


class PlacementReportOut(BaseModel):
    status: PlacementReportStatus


class PlacementBatchReportItemIn(BaseModel):
    placement_id: UUID
    op_version: int = Field(ge=1)
    applied_state: PlacementAppliedState


class PlacementBatchReportIn(BaseModel):
    items: list[PlacementBatchReportItemIn] = Field(default_factory=list)


class PlacementBatchReportItemOut(BaseModel):
    placement_id: UUID
    status: PlacementReportStatus


class PlacementBatchReportOut(BaseModel):
    items: list[PlacementBatchReportItemOut]


class PlacementAssignmentOut(BaseModel):
    id: UUID
    key_id: UUID
    op_version: int
    desired_state: PlacementDesiredState
    applied_state: PlacementAppliedState
    applied_version: int
    backend_node_id: UUID

    protocol: VpnProtocol
    client_id: str
    transport: VpnTransport
    valid_until: datetime | None
    is_revoked: bool
    updated_at: datetime | None = None
    backend_internal_wg_ip: str
    backend_xray_api_port: int

    model_config = ConfigDict(from_attributes=True)


class PlacementPageOut(BaseModel):
    items: list[PlacementAssignmentOut]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor in format '<op_version>:<placement_id>' for stable pagination.",
        examples=["12:f2132b71-b4aa-470d-9586-cb907050ca52"],
    )


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
