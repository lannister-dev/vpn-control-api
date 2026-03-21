from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class TrafficUsage(Base):
    __tablename__ = "traffic_usage"

    key_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_key.id"), nullable=False)
    delta_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reported_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_traffic_usage_key_id", "key_id"),
        Index("ix_traffic_usage_created_at", "created_at"),
    )


class KeyNodeTrafficCounter(Base):
    """Per-(key, node) cumulative counter to correctly compute deltas
    when the same key is placed on multiple VPN nodes."""

    __tablename__ = "key_node_traffic_counter"

    key_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_key.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_reported_total_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0"),
    )

    __table_args__ = (
        UniqueConstraint("key_id", "node_id", name="uq_key_node_traffic_counter"),
        Index("ix_key_node_traffic_counter_key_id", "key_id"),
    )
