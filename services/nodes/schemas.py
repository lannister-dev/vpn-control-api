from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class NodeAgentStateCreate(BaseModel):
    node_id: str
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: Dict = Field(default_factory=dict)


class NodeAgentStateUpdate(BaseModel):
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: Dict = Field(default_factory=dict)


class NodeHeartbeatIn(BaseModel):
    agent_version: str
    is_healthy: bool
    details: Dict = Field(default_factory=dict)


class NodeAgentStateOut(BaseModel):
    node_id: str
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: Dict

    model_config = ConfigDict(from_attributes=True)


class NodeHeartbeatInternal(BaseModel):
    node_id: str
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: Dict


class KeyAssignmentCreate(BaseModel):
    key_id: UUID
    node_id: UUID
    desired_state: str


class KeyAssignmentUpdate(BaseModel):
    desired_state: str | None = None


class AssignmentReportIn(BaseModel):
    applied_state: str
    status: str
    last_error: Optional[str] = None
    last_applied_at: datetime


class AssignmentOut(BaseModel):
    id: UUID
    key_id: UUID
    desired_state: str
    applied_state: str | None
    status: str | None

    protocol: str
    transport: str
    client_id: str

    valid_until: datetime | None
    traffic_limit_mb: int | None
    is_revoked: bool

    model_config = ConfigDict(from_attributes=True)