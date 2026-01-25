from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------- VpnKey ---------------------
class VpnProtocol(str, Enum):
    vless = "vless"


class VpnTransport(str, Enum):
    ws = "ws"
    xhttp = "xhttp"
    tcp = "tcp"


class VpnKeyCreate(BaseModel):
    user_id: UUID
    protocol: VpnProtocol
    transport: VpnTransport
    valid_until: datetime
    traffic_limit_mb: int = Field(gt=0)


class VpnKeyOut(BaseModel):
    id: UUID
    protocol: VpnProtocol
    transport: VpnTransport
    client_id: str
    valid_until: datetime
    traffic_limit_mb: int
    is_revoked: bool

    model_config = ConfigDict(from_attributes=True)


class VpnKeyInternalCreate(BaseModel):
    user_id: UUID
    protocol: VpnProtocol
    transport: VpnTransport
    client_id: str
    valid_until: datetime
    traffic_limit_mb: int
    is_revoked: bool = False

    @field_validator("valid_until")
    @classmethod
    def normalize(cls, v: datetime) -> datetime:
        if v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class VpnKeyInternal(BaseModel):
    protocol: VpnProtocol
    transport: VpnTransport
    client_id: str
    valid_until: datetime | None
    traffic_limit_mb: int | None
    is_revoked: bool

    model_config = ConfigDict(from_attributes=True)


# ---------------- KeyAssignment ---------------------

class AssignmentDesiredState(str, Enum):
    present = "present"
    absent = "absent"


class AssignmentAppliedState(str, Enum):
    present = "present"
    absent = "absent"


class AssignmentStatus(str, Enum):
    pending = "pending"
    applied = "applied"
    error = "error"


class KeyAssignmentCreate(BaseModel):
    node_id: UUID
    desired_state: AssignmentDesiredState


class KeyAssignmentInternalCreate(BaseModel):
    key_id: UUID
    node_id: UUID
    desired_state: AssignmentDesiredState
    applied_state: AssignmentAppliedState = AssignmentStatus.pending
    status: AssignmentStatus = AssignmentStatus.pending


class KeyAssignmentUpdate(BaseModel):
    desired_state: AssignmentDesiredState


class AssignmentReportIn(BaseModel):
    applied_state: AssignmentAppliedState
    status: AssignmentStatus
    last_error: Optional[str] = None
    last_applied_at: datetime


class AssignmentOut(BaseModel):
    id: UUID
    key_id: UUID
    desired_state: AssignmentDesiredState
    applied_state: AssignmentAppliedState | None
    status: AssignmentStatus | None

    protocol: VpnProtocol
    transport: VpnTransport
    client_id: str

    valid_until: datetime | None
    traffic_limit_mb: int | None
    is_revoked: bool

    model_config = ConfigDict(from_attributes=True)
