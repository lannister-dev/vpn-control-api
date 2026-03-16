from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class NodeTransportOutbox(Base):
    __tablename__ = "node_transport_outbox"

    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    aggregate_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    op_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str] = mapped_column(String(length=255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    message_id: Mapped[str] = mapped_column(String(length=255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NodeTransportEventLog(Base):
    __tablename__ = "node_transport_event_log"

    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    event_id: Mapped[str] = mapped_column(String(length=255), nullable=False, unique=True)
    subject: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NodeTransportState(Base):
    __tablename__ = "node_transport_state"

    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False, unique=True)
    current_epoch: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_snapshot_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    last_snapshot_request_event_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    last_snapshot_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_snapshot_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_snapshot_reason: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    last_command_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_command_message_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    last_result_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result_event_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    last_heartbeat_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_report_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("node_id", name="uq_node_transport_state_node"),
    )
