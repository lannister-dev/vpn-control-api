from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Overview ──────────────────────────────────────────────────

class ConsumerTaskStatus(BaseModel):
    name: str
    running: bool
    error: str | None = None


class OutboxSummary(BaseModel):
    pending: int = 0
    failed: int = 0
    publishing: int = 0
    published_24h: int = 0


class EventLogSummary(BaseModel):
    total_24h: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class TransportOverviewOut(BaseModel):
    generated_at: datetime
    nats_connected: bool
    uptime_s: float | None = None
    consumer_tasks: list[ConsumerTaskStatus]
    outbox: OutboxSummary
    events: EventLogSummary


# ── Transport node list ──────────────────────────────────────

class TransportNodeOut(BaseModel):
    node_id: UUID
    name: str
    region: str
    current_epoch: int = 0
    last_snapshot_id: str | None = None
    last_snapshot_reason: str | None = None
    last_snapshot_at: datetime | None = None
    last_command_published_at: datetime | None = None
    last_result_received_at: datetime | None = None
    last_heartbeat_received_at: datetime | None = None
    last_sync_report_received_at: datetime | None = None
    outbox_pending: int = 0
    outbox_failed: int = 0
    communication_lag_s: float | None = None
    health_verdict: str = "dead"


class TransportNodeListOut(BaseModel):
    items: list[TransportNodeOut]


# ── Transport node detail ────────────────────────────────────

class TransportEventOut(BaseModel):
    id: UUID
    event_type: str
    event_id: str
    subject: str | None = None
    processed_at: datetime
    payload: dict = Field(default_factory=dict)


class TransportOutboxItemOut(BaseModel):
    id: UUID
    event_type: str
    message_id: str
    status: str
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime
    published_at: datetime | None = None
    next_retry_at: datetime | None = None


class TransportNodeDetailOut(TransportNodeOut):
    last_snapshot_requested_at: datetime | None = None
    last_snapshot_generated_at: datetime | None = None
    recent_events: list[TransportEventOut] = Field(default_factory=list)
    outbox_items: list[TransportOutboxItemOut] = Field(default_factory=list)


# ── Outbox browser ───────────────────────────────────────────

class OutboxItemWithNodeOut(TransportOutboxItemOut):
    node_id: UUID
    node_name: str | None = None


class OutboxListOut(BaseModel):
    items: list[OutboxItemWithNodeOut]
    total: int
    limit: int
    offset: int


class OutboxRetryOut(BaseModel):
    ok: bool = True


class OutboxRetryAllOut(BaseModel):
    retried_count: int


class OutboxBreakdownItem(BaseModel):
    event_type: str
    status: str
    count: int


class OutboxBreakdownOut(BaseModel):
    items: list[OutboxBreakdownItem]


# ── Event log browser ────────────────────────────────────────

class EventWithNodeOut(TransportEventOut):
    node_id: UUID
    node_name: str | None = None


class EventLogListOut(BaseModel):
    items: list[EventWithNodeOut]
    total: int
    limit: int
    offset: int


# ── Force snapshot ────────────────────────────────────────────

class ForceSnapshotOut(BaseModel):
    ok: bool = True
    epoch: int
    snapshot_id: str


# ── Cleanup ──────────────────────────────────────────────────

class TransportCleanupOut(BaseModel):
    deleted_outbox: int = 0
    deleted_events: int = 0
    retention_days: int
