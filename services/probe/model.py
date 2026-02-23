from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class ProbeSignal(Base):
    __tablename__ = "probe_signal"

    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(length=64), nullable=False)
    is_reachable: Mapped[bool] = mapped_column(nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_probe_signal_node_id", "node_id"),
        Index("ix_probe_signal_source", "source"),
        Index("ix_probe_signal_checked_at", "checked_at"),
        Index("ix_probe_signal_node_source_checked_at", "node_id", "source", "checked_at"),
    )
