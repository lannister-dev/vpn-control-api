from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BackendPeerStatus(str, Enum):
    active = "active"
    inactive = "inactive"


class BackendPeerAppliedState(str, Enum):
    pending = "pending"
    applied = "applied"
    error = "error"


class BackendPeerUpsertIn(BaseModel):
    backend_node_id: UUID
    gateway_node_id: UUID
    internal_uuid: UUID | None = None
    status: BackendPeerStatus = BackendPeerStatus.active


class BackendPeerOut(BaseModel):
    id: UUID
    backend_node_id: UUID
    gateway_node_id: UUID
    internal_uuid: str
    status: BackendPeerStatus
    applied_state: BackendPeerAppliedState
    op_version: int
    applied_version: int
    last_error: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackendPeerPageItemOut(BaseModel):
    id: UUID
    backend_node_id: UUID
    gateway_node_id: UUID
    internal_uuid: str
    status: BackendPeerStatus
    applied_state: BackendPeerAppliedState
    op_version: int
    applied_version: int
    last_error: str | None
    gateway_public_domain: str


class BackendPeerPageOut(BaseModel):
    items: list[BackendPeerPageItemOut]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor in format '<op_version>:<peer_id>' for stable pagination.",
        examples=["12:f2132b71-b4aa-470d-9586-cb907050ca52"],
    )


class BackendPeerGatewayItemOut(BaseModel):
    id: UUID
    backend_node_id: UUID
    internal_uuid: str
    status: BackendPeerStatus
    applied_state: BackendPeerAppliedState
    op_version: int
    applied_version: int
    last_error: str | None
    backend_internal_wg_ip: str
    backend_xray_api_port: int


class BackendPeerGatewayPageOut(BaseModel):
    items: list[BackendPeerGatewayItemOut]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor in format '<op_version>:<peer_id>' for stable pagination.",
        examples=["12:f2132b71-b4aa-470d-9586-cb907050ca52"],
    )


class BackendPeerReportIn(BaseModel):
    op_version: int = Field(ge=1)
    applied_state: BackendPeerAppliedState
    last_error: str | None = Field(default=None, max_length=255)


BackendPeerReportStatus = Literal[
    "applied",
    "pending",
    "error",
    "skipped_stale",
    "skipped_idempotent",
]


class BackendPeerReportOut(BaseModel):
    status: BackendPeerReportStatus


class BackendPeerReportUpdate(BaseModel):
    applied_state: BackendPeerAppliedState
    applied_version: int = Field(ge=0)
    last_error: str | None = Field(default=None, max_length=255)
    updated_at: datetime


class BackendPeerEnsureUpdate(BaseModel):
    status: BackendPeerStatus
    applied_state: BackendPeerAppliedState
    op_version: int = Field(ge=1)
    is_active: bool
    last_error: str | None = Field(default=None, max_length=255)
    updated_at: datetime


class BackendPeerInternalCreate(BaseModel):
    backend_node_id: UUID
    gateway_node_id: UUID
    internal_uuid: str
    status: BackendPeerStatus
    applied_state: BackendPeerAppliedState
    op_version: int = Field(ge=1)
    applied_version: int = Field(ge=0)
    last_error: str | None = Field(default=None, max_length=255)
    is_active: bool


class BackendPeerEnsureIn(BaseModel):
    backend_node_id: UUID
    gateway_node_id: UUID
