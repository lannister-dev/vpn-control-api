from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransportDesiredState(str, Enum):
    active = "active"
    inactive = "inactive"


class TransportAppliedState(str, Enum):
    pending = "pending"
    applied = "applied"
    error = "error"


class TransportReportStatus(str, Enum):
    applied = "applied"
    pending = "pending"
    error = "error"
    skipped_stale = "skipped_stale"
    skipped_idempotent = "skipped_idempotent"


class TransportProtocol(str, Enum):
    vless = "vless"


class TransportVpnTransport(str, Enum):
    ws = "ws"
    xhttp = "xhttp"
    tcp = "tcp"
    reality = "reality"


class SnapshotRequestReason(str, Enum):
    startup = "startup"
    xray_restart = "xray_restart"
    redelivery_gap = "redelivery_gap"
    operator_forced = "operator_forced"


class AgentEnvelope(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    node_id: str
    emitted_at: datetime
    snapshot_id: str | None = None
    epoch: int | None = Field(default=None, ge=0)


class PlacementCommandEvent(AgentEnvelope):
    event_id: str
    placement_id: str
    key_id: str
    op_version: int = Field(ge=1)
    desired_state: TransportDesiredState
    backend_node_id: str
    protocol: TransportProtocol = Field(default=TransportProtocol.vless)
    transport: TransportVpnTransport = Field(default=TransportVpnTransport.ws)
    client_id: str
    is_revoked: bool = False
    snapshot_complete: bool = False
    valid_until: datetime | None = None
    updated_at: datetime | None = None


class PlacementApplyResultEvent(AgentEnvelope):
    event_id: str
    placement_id: str
    op_version: int = Field(ge=1)
    applied_state: TransportAppliedState
    report_status: TransportReportStatus | None = None
    retryable: bool = False
    error: str | None = None
    inventory_hash: str | None = None
    inventory_count: int | None = Field(default=None, ge=0)


class PlacementApplyAckEvent(AgentEnvelope):
    event_id: str
    placement_id: str
    op_version: int = Field(ge=1)
    status: TransportReportStatus
    error: str | None = None


class SnapshotRequestEvent(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    node_id: str
    requested_at: datetime
    reason: SnapshotRequestReason
    known_snapshot_id: str | None = None
    last_command_stream_seq: int | None = Field(default=None, ge=0)
    last_seen_xray_uptime: int | None = Field(default=None, ge=0)


class SnapshotChunkEvent(AgentEnvelope):
    chunk_index: int = Field(ge=0)
    is_last_chunk: bool = False
    items: list[PlacementCommandEvent] = Field(default_factory=list)


class HeartbeatPoolHealth(BaseModel):
    slots_total: int = Field(ge=0)
    slots_active: int = Field(ge=0)
    desired_backends: int = Field(ge=0)
    dropped_overflow: int = Field(ge=0, default=0)
    last_apply_ok: bool = True
    last_apply_error: str | None = None
    consecutive_apply_failures: int = Field(ge=0, default=0)
    last_applied_generation: int = Field(ge=0, default=0)
    last_applied_at: datetime | None = None


class HeartbeatUpstreamHealth(BaseModel):
    configured: bool = False
    last_apply_ok: bool = True
    last_apply_error: str | None = None
    consecutive_apply_failures: int = Field(ge=0, default=0)
    upstream_node_id: str | None = None
    upstream_host: str | None = None
    upstream_addr: str | None = None
    last_applied_at: datetime | None = None


class HeartbeatEvent(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    event_id: str
    node_id: str
    emitted_at: datetime
    agent_version: str
    is_healthy: bool
    ready: bool
    last_error: str | None = None
    poll_count: int = Field(ge=0)
    applied: int = Field(ge=0)
    failed: int = Field(ge=0)
    cpu_pct: float | None = Field(default=None, ge=0, le=100)
    mem_pct: float | None = Field(default=None, ge=0, le=100)
    pool: HeartbeatPoolHealth | None = None
    upstream: HeartbeatUpstreamHealth | None = None


class SyncReportEvent(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    event_id: str
    node_id: str
    emitted_at: datetime
    synced_count: int = Field(ge=0)
    config_version: int | None = Field(default=None, ge=0)
    inventory_hash: str | None = None
    inventory_count: int | None = Field(default=None, ge=0)
    full_resync_completed: bool = False


class SyncReportAckStatus(str, Enum):
    accepted = "accepted"
    skipped = "skipped"


class SyncReportAckEvent(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    event_id: str
    node_id: str
    emitted_at: datetime
    status: SyncReportAckStatus
    error: str | None = None


class AgentSubjects:
    def __init__(
        self,
        *,
        command_prefix: str,
        result_prefix: str,
        snapshot_prefix: str,
        heartbeat_prefix: str,
        sync_report_prefix: str,
    ) -> None:
        self._command_prefix = command_prefix.rstrip(".")
        self._result_prefix = result_prefix.rstrip(".")
        self._snapshot_prefix = snapshot_prefix.rstrip(".")
        self._heartbeat_prefix = heartbeat_prefix.rstrip(".")
        self._sync_report_prefix = sync_report_prefix.rstrip(".")

    def placement_command(self, node_id: str) -> str:
        return f"{self._command_prefix}.{node_id}.commands"

    def placement_result(self, node_id: str) -> str:
        return f"{self._result_prefix}.{node_id}.results"

    def placement_result_ack(self, node_id: str) -> str:
        return f"{self._result_prefix}.{node_id}.acks"

    def snapshot_request(self, node_id: str) -> str:
        return f"{self._snapshot_prefix}.{node_id}.request"

    def snapshot_chunk(self, node_id: str) -> str:
        return f"{self._snapshot_prefix}.{node_id}.chunks"

    def heartbeat(self, node_id: str) -> str:
        return f"{self._heartbeat_prefix}.{node_id}.events"

    def sync_report(self, node_id: str) -> str:
        return f"{self._sync_report_prefix}.{node_id}.events"

    def sync_report_ack(self, node_id: str) -> str:
        return f"{self._sync_report_prefix}.{node_id}.acks"

    def upstream_changed(self, node_id: str) -> str:
        return f"{self._command_prefix}.{node_id}.upstream"

    def pool_changed(self, node_id: str) -> str:
        return f"{self._command_prefix}.{node_id}.pool"


class UpstreamChangedPayload(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    event_id: str
    node_id: str
    emitted_at: datetime
    upstream_node_id: str
    upstream_public_domain: str
    upstream_reality_ip: str | None = None


class OutboxEnqueueItem(BaseModel):
    node_id: UUID
    event_type: str = Field(min_length=1, max_length=64)
    aggregate_id: UUID | None = None
    op_version: int = None
    subject: str = Field(min_length=1, max_length=255)
    payload: dict
    message_id: str = Field(min_length=1, max_length=255)
    status: str = Field(default="pending", min_length=1, max_length=32)


class PlacementCommandPayload(BaseModel):
    placement_id: UUID
    key_id: UUID
    node_id: UUID
    backend_node_id: UUID
    op_version: int = Field(ge=1)
    desired_state: TransportDesiredState
    protocol: TransportProtocol
    transport: TransportVpnTransport
    client_id: str
    is_revoked: bool = False
    valid_until: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RuntimeTaskStatus(BaseModel):
    name: str
    running: bool
    error: str | None = None


class RuntimeStatus(BaseModel):
    nats_connected: bool
    uptime_s: float | None = None
    tasks: list[RuntimeTaskStatus] = Field(default_factory=list)


class TransportEventLogInsert(BaseModel):
    node_id: UUID
    event_type: str
    event_id: str
    subject: str | None = None
    payload: dict
    processed_at: datetime


class PlacementResultApply(BaseModel):
    id: UUID
    op_version: int = Field(ge=1)
    backend_node_id: UUID
    applied_state: str
    applied_version: int
    updated_at: datetime
