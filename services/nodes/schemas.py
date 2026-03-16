from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class VpnNodeCreate(BaseModel):
    name: str
    region: str
    public_domain: str
    reality_ip: str | None = None
    internal_wg_ip: str
    node_key: str | None = None
    xray_api_port: int = 10085
    agent_port: int = 9000
    auth_token_hash: str
    is_enabled: bool = True
    is_draining: bool = False
    capacity: int = 100


class VpnNodeUpdate(BaseModel):
    name: str | None = None
    region: str | None = None
    public_domain: str | None = None
    reality_ip: str | None = None
    internal_wg_ip: str | None = None
    node_key: str | None = None
    xray_api_port: int | None = None
    agent_port: int | None = None
    auth_token_hash: str | None = None
    is_enabled: bool | None = None
    is_draining: bool | None = None
    capacity: int | None = None


class AdminNodeUpdateIn(BaseModel):
    name: str | None = None
    region: str | None = None
    public_domain: str | None = None
    reality_ip: str | None = None
    capacity: int | None = Field(default=None, ge=1, le=10000)
    is_enabled: bool | None = None
    is_draining: bool | None = None
    model_config = ConfigDict(extra="forbid")


class VpnNodeOut(BaseModel):
    id: UUID
    name: str
    region: str
    public_domain: str
    reality_ip: str | None = None
    internal_wg_ip: str
    node_key: str | None = None
    xray_api_port: int
    agent_port: int
    is_enabled: bool
    is_draining: bool
    capacity: int

    model_config = ConfigDict(from_attributes=True)

class HeartbeatStats(BaseModel):
    poll_count: int
    applied: int
    failed: int


class HeartbeatRuntime(BaseModel):
    ready: bool
    last_error: Optional[str] = None


class HeartbeatDetails(BaseModel):
    runtime: HeartbeatRuntime
    stats: HeartbeatStats


class NodeSyncDetails(BaseModel):
    synced_count: int = Field(ge=0)
    reported_at: datetime
    inventory_hash: str | None = None
    inventory_count: int | None = Field(default=None, ge=0)
    full_resync_completed: bool | None = None


class NodeAgentDetails(BaseModel):
    runtime: HeartbeatRuntime | None = None
    stats: HeartbeatStats | None = None
    sync: NodeSyncDetails | None = None

    model_config = ConfigDict(extra="allow")


class NodeHeartbeatMeta(BaseModel):
    consecutive_unhealthy: int = Field(default=0, ge=0)
    consecutive_healthy: int = Field(default=0, ge=0)
    drain_reason: str | None = None

    model_config = ConfigDict(extra="ignore")


class NodeHeartbeatIn(BaseModel):
    agent_version: str
    is_healthy: bool
    details: HeartbeatDetails


class NodeSyncReportIn(BaseModel):
    synced_count: int = Field(ge=0)
    config_version: int | None = Field(default=None, ge=0)
    inventory_hash: str | None = Field(default=None, min_length=1, max_length=128)
    inventory_count: int | None = Field(default=None, ge=0)
    full_resync_completed: bool | None = None


class NodeSyncReportStatus(str, Enum):
    accepted = "accepted"
    skipped = "skipped"


class NodeSyncReportOut(BaseModel):
    status: NodeSyncReportStatus


class NodeAgentStateOut(BaseModel):
    node_id: str
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: dict[str, object]

    model_config = ConfigDict(from_attributes=True)


class NodeHeartbeatInternal(BaseModel):
    node_id: str
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: dict[str, object]


class NodeAgentInitialOut(BaseModel):
    node_id: str
    node_auth_token: str
    agent_instance_id: str
    full_resync_required: bool = True


class NodeAgentStateCreate(BaseModel):
    node_id: UUID
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    last_sync_at: datetime | None
    last_config_version: int | None = Field(default=None, ge=0)
    details: dict[str, object]


class NodeAgentStateUpdate(BaseModel):
    agent_version: str | None = None
    is_healthy: bool | None = None
    last_seen_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_config_version: int | None = Field(default=None, ge=0)
    details: dict[str, object] | None = None
