from __future__ import annotations

from datetime import datetime, timezone

from services.admin_transport.read_models import (
    TransportEventRow,
    TransportEventWithNodeRow,
    TransportNodeRow,
    TransportOutboxRow,
    TransportOutboxWithNodeRow,
)
from services.admin_transport.schemas import (
    EventWithNodeOut,
    OutboxItemWithNodeOut,
    TransportEventOut,
    TransportNodeOut,
    TransportOutboxItemOut,
)

_SENSITIVE_KEYS = frozenset({"token", "hash", "secret", "password", "auth"})


def sanitize_payload(payload: dict | None) -> dict:
    if not payload:
        return {}

    cleaned: dict = {}
    for key, value in payload.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in _SENSITIVE_KEYS):
            cleaned[key] = "***"
        elif isinstance(value, dict):
            cleaned[key] = sanitize_payload(value)
        else:
            cleaned[key] = value
    return cleaned


def compute_transport_lag(row: TransportNodeRow, *, now: datetime) -> float | None:
    timestamps = []
    for timestamp in (
        row.last_heartbeat_received_at,
        row.last_result_received_at,
        row.last_sync_report_received_at,
    ):
        if timestamp is None:
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamps.append(timestamp)

    if not timestamps:
        return None

    latest = max(timestamps)
    return max(0.0, (now - latest).total_seconds())


def build_health_verdict(lag_s: float | None) -> str:
    if lag_s is None:
        return "dead"
    if lag_s < 30:
        return "ok"
    if lag_s < 90:
        return "lag"
    if lag_s < 300:
        return "silent"
    return "dead"


def to_transport_node_out(row: TransportNodeRow, *, now: datetime) -> TransportNodeOut:
    lag_s = compute_transport_lag(row, now=now)
    return TransportNodeOut(
        node_id=row.node_id,
        name=row.name or "",
        region=row.region or "",
        current_epoch=row.current_epoch,
        last_snapshot_id=row.last_snapshot_id,
        last_snapshot_reason=row.last_snapshot_reason,
        last_snapshot_at=row.last_snapshot_at,
        last_command_published_at=row.last_command_published_at,
        last_result_received_at=row.last_result_received_at,
        last_heartbeat_received_at=row.last_heartbeat_received_at,
        last_sync_report_received_at=row.last_sync_report_received_at,
        outbox_pending=row.outbox_pending,
        outbox_failed=row.outbox_failed,
        communication_lag_s=lag_s,
        health_verdict=build_health_verdict(lag_s),
    )


def to_transport_event_out(row: TransportEventRow) -> TransportEventOut:
    return TransportEventOut(
        id=row.id,
        event_type=row.event_type,
        event_id=row.event_id,
        subject=row.subject,
        processed_at=row.processed_at,
        payload=sanitize_payload(row.payload),
    )


def to_transport_outbox_item_out(row: TransportOutboxRow) -> TransportOutboxItemOut:
    return TransportOutboxItemOut(
        id=row.id,
        event_type=row.event_type,
        message_id=row.message_id,
        status=row.status,
        attempts=row.attempts,
        last_error=row.last_error,
        created_at=row.created_at,
        published_at=row.published_at,
        next_retry_at=row.next_retry_at,
    )


def to_outbox_item_with_node_out(row: TransportOutboxWithNodeRow) -> OutboxItemWithNodeOut:
    return OutboxItemWithNodeOut(
        node_id=row.node_id,
        node_name=row.node_name,
        **to_transport_outbox_item_out(row).model_dump(),
    )


def to_event_with_node_out(row: TransportEventWithNodeRow) -> EventWithNodeOut:
    return EventWithNodeOut(
        node_id=row.node_id,
        node_name=row.node_name,
        **to_transport_event_out(row).model_dump(),
    )
