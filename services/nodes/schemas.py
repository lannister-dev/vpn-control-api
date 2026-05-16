from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VpnNodeCreate(BaseModel):
    name: str
    role: str = Field(default="backend", min_length=1, max_length=16)
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
    zone: str | None = None


class VpnNodeUpdate(BaseModel):
    name: str | None = None
    role: str | None = Field(default=None, min_length=1, max_length=16)
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
    drain_source: str | None = Field(default=None, max_length=16)
    capacity: int | None = None
    wg_public_key: str | None = Field(default=None, max_length=64)
    wg_listen_port: int | None = Field(default=None, ge=1, le=65535)
    bootstrap_token_expires_at: datetime | None = None
    bootstrapped_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class AdminNodeUpdateIn(BaseModel):
    name: str | None = None
    role: str | None = Field(default=None, min_length=1, max_length=16)
    region: str | None = None
    public_domain: str | None = None
    reality_ip: str | None = None
    upstream_node_id: UUID | None = None
    capacity: int | None = Field(default=None, ge=1, le=10000)
    zone: str | None = Field(default=None, max_length=32)
    is_enabled: bool | None = None
    is_draining: bool | None = None
    model_config = ConfigDict(extra="forbid")


class VpnNodeOut(BaseModel):
    id: UUID
    name: str
    role: str
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
    zone: str | None = None
    upstream_node_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)

class HeartbeatStats(BaseModel):
    poll_count: int
    applied: int
    failed: int
    cpu_pct: float | None = None
    mem_pct: float | None = None


class HeartbeatRuntime(BaseModel):
    ready: bool
    last_error: str | None = None


class HeartbeatPool(BaseModel):
    slots_total: int = Field(ge=0)
    slots_active: int = Field(ge=0)
    desired_backends: int = Field(ge=0)
    dropped_overflow: int = Field(ge=0, default=0)
    last_apply_ok: bool = True
    last_apply_error: str | None = None
    consecutive_apply_failures: int = Field(ge=0, default=0)
    last_applied_generation: int = Field(ge=0, default=0)
    last_applied_at: datetime | None = None


class HeartbeatUpstream(BaseModel):
    configured: bool = False
    last_apply_ok: bool = True
    last_apply_error: str | None = None
    consecutive_apply_failures: int = Field(ge=0, default=0)
    upstream_node_id: str | None = None
    upstream_host: str | None = None
    upstream_addr: str | None = None
    last_applied_at: datetime | None = None


class HeartbeatDetails(BaseModel):
    runtime: HeartbeatRuntime
    stats: HeartbeatStats
    pool: HeartbeatPool | None = None
    upstream: HeartbeatUpstream | None = None


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
    pool: HeartbeatPool | None = None
    upstream: HeartbeatUpstream | None = None

    model_config = ConfigDict(extra="allow")


class NodeHeartbeatMeta(BaseModel):
    consecutive_unhealthy: int = Field(default=0, ge=0)
    consecutive_healthy: int = Field(default=0, ge=0)
    drain_reason: str | None = None
    drained_at: datetime | None = None

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


class AdminNodeCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=16)
    region: str = Field(min_length=1, max_length=32)
    public_domain: str = Field(default="", max_length=255)
    reality_ip: str | None = Field(default=None, max_length=64)
    internal_wg_ip: str = Field(default="", max_length=64)
    capacity: int = Field(default=100, ge=1, le=10000)
    zone: str | None = Field(default=None, max_length=32)

    model_config = ConfigDict(extra="forbid")


class AdminNodeCreateOut(BaseModel):
    node: VpnNodeOut
    bootstrap_token: str
    bootstrap_token_expires_at: datetime
    install_command: str

    model_config = ConfigDict(from_attributes=False)


class AdminNodeRotateBootstrapOut(BaseModel):
    node_id: UUID
    bootstrap_token: str
    bootstrap_token_expires_at: datetime
    install_command: str


class NodeBootstrapCompleteIn(BaseModel):
    k3s_node_name: str | None = Field(default=None, max_length=64)
    labels_applied: dict[str, str] | None = None

    model_config = ConfigDict(extra="forbid")


class NodeBootstrapCompleteOut(BaseModel):
    node_id: UUID
    bootstrapped_at: datetime


class NodeAgentStateCreate(BaseModel):
    node_id: UUID
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    last_sync_at: datetime | None
    last_config_version: int | None = Field(default=None, ge=0)
    details: dict[str, object]


class NodeUpstreamUpdate(BaseModel):
    upstream_node_id: UUID
    updated_at: datetime


class NodeAgentStateUpdate(BaseModel):
    agent_version: str | None = None
    is_healthy: bool | None = None
    last_seen_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_config_version: int | None = Field(default=None, ge=0)
    details: dict[str, object] | None = None
