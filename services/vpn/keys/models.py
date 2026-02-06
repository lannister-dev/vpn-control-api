from __future__ import annotations
from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Boolean, text, Index, Integer, DateTime
from sqlalchemy.orm import mapped_column, Mapped, relationship

from shared.database.base_model import Base


class VpnKey(Base):
    __tablename__ = "vpn_key"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"))
    protocol: Mapped[str] = mapped_column(String(length=16))  # vless
    transport: Mapped[str] = mapped_column(String(length=16))  # ws / xhttp / tcp
    client_id: Mapped[str] = mapped_column(String(length=36), unique=True, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    traffic_limit_mb: Mapped[int] = mapped_column(nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)

    user: Mapped["User"] = relationship(back_populates="keys")
    assignments: Mapped[list["KeyAssignment"]] = relationship(
        back_populates="key",
        cascade="all, delete-orphan"
    )
    __table_args__ = (
        Index("ix_vpn_key_user_id", "user_id"),
        Index("ix_vpn_key_valid_until", "valid_until"),
        Index("ix_vpn_key_is_revoked", "is_revoked"),
    )


class KeyAssignment(Base):
    __tablename__ = "key_assignment"

    key_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_key.id"))
    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"))
    desired_state: Mapped[str] = mapped_column(String(length=16))
    applied_state: Mapped[str] = mapped_column(String(length=16))
    status: Mapped[str] = mapped_column(String(length=16), server_default=text("'pending'"), nullable=False)
    last_error: Mapped[str] = mapped_column(nullable=True)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    op_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    key: Mapped["VpnKey"] = relationship(back_populates="assignments")
    node: Mapped["VpnNode"] = relationship(back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("key_id", "node_id", name="uq_key_node"),
        Index("ix_key_assignment_node_id", "node_id"),
        Index("ix_key_assignment_key_id", "key_id"),
        Index("ix_key_assignment_status", "status"),
        Index("ix_key_assignment_next_retry_at", "next_retry_at"),
    )
