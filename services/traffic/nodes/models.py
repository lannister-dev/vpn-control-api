from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class NodeTrafficUsage(Base):
    __tablename__ = "node_traffic_usage"

    entry_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vpn_node.id", ondelete="CASCADE"),
        nullable=True,
    )
    backend_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vpn_node.id", ondelete="SET NULL"),
        nullable=True,
    )
    bytes_in: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_out: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    active_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_node_traffic_entry_created", "entry_node_id", "created_at"),
        Index("ix_node_traffic_backend_created", "backend_node_id", "created_at"),
        Index("ix_node_traffic_created_at", "created_at"),
    )
