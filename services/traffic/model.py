from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index
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
