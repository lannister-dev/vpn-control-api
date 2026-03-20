from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OutboxSummaryRow(BaseModel):
    pending: int = 0
    failed: int = 0
    publishing: int = 0
    published_24h: int = 0


class EventLogSummaryRow(BaseModel):
    total_24h: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class TransportNodeRow(BaseModel):
    node_id: UUID
    name: str | None = None
    region: str | None = None
    current_epoch: int = 0
    last_snapshot_id: str | None = None
    last_snapshot_reason: str | None = None
    last_snapshot_at: datetime | None = None
    last_snapshot_requested_at: datetime | None = None
    last_snapshot_generated_at: datetime | None = None
    last_command_published_at: datetime | None = None
    last_result_received_at: datetime | None = None
    last_heartbeat_received_at: datetime | None = None
    last_sync_report_received_at: datetime | None = None
    outbox_pending: int = 0
    outbox_failed: int = 0


class TransportEventRow(BaseModel):
    id: UUID
    event_type: str
    event_id: str
    subject: str | None = None
    processed_at: datetime
    payload: dict = Field(default_factory=dict)


class TransportEventWithNodeRow(TransportEventRow):
    node_id: UUID
    node_name: str | None = None


class TransportOutboxRow(BaseModel):
    id: UUID
    event_type: str
    message_id: str
    status: str
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime
    published_at: datetime | None = None
    next_retry_at: datetime | None = None


class TransportOutboxWithNodeRow(TransportOutboxRow):
    node_id: UUID
    node_name: str | None = None
