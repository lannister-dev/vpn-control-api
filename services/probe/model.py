from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class ProbeSignal(Base):
    __tablename__ = "probe_signal"

    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False)
    route_id: Mapped[UUID | None] = mapped_column(ForeignKey("route.id"), nullable=True)
    transport_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transport_profile.id"),
        nullable=True,
    )
    transport_kind: Mapped[str | None] = mapped_column(String(length=16), nullable=True)
    probe_kind: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        server_default=text("'tcp_connect'"),
    )
    target_host: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    target_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_phase: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    source: Mapped[str] = mapped_column(String(length=64), nullable=False)
    is_reachable: Mapped[bool] = mapped_column(nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "target_port IS NULL OR (target_port >= 1 AND target_port <= 65535)",
            name="ck_probe_signal_target_port_range",
        ),
        Index("ix_probe_signal_node_id", "node_id"),
        Index("ix_probe_signal_route_id", "route_id"),
        Index("ix_probe_signal_transport_profile_id", "transport_profile_id"),
        Index("ix_probe_signal_source", "source"),
        Index("ix_probe_signal_checked_at", "checked_at"),
        Index("ix_probe_signal_node_source_checked_at", "node_id", "source", "checked_at"),
        Index("ix_probe_signal_route_source_checked_at", "route_id", "source", "checked_at"),
    )
