from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.base_model import Base


class VpnKey(Base):
    __tablename__ = "vpn_key"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    protocol: Mapped[str] = mapped_column(String(length=16))  # vless
    transport: Mapped[str] = mapped_column(String(length=16))  # ws / xhttp / reality
    client_id: Mapped[str] = mapped_column(String(length=36), unique=True, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    traffic_limit_mb: Mapped[int] = mapped_column(nullable=False)
    used_traffic_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    subscription_id: Mapped[UUID | None] = mapped_column(ForeignKey("subscription.id"), nullable=True)

    user: Mapped[User] = relationship(back_populates="keys")
    subscription: Mapped[Subscription] = relationship(
        foreign_keys=[subscription_id], lazy="select",
    )
    assignments: Mapped[list[KeyAssignment]] = relationship(
        back_populates="key",
        cascade="all, delete-orphan"
    )
    __table_args__ = (
        Index("ix_vpn_key_user_id", "user_id"),
        Index("ix_vpn_key_valid_until", "valid_until"),
        Index("ix_vpn_key_is_revoked", "is_revoked"),
        Index("ix_vpn_key_subscription_id", "subscription_id"),
    )


class KeyAssignment(Base):
    __tablename__ = "key_assignment"

    key_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_key.id", ondelete="CASCADE"))
    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"))
    desired_state: Mapped[str] = mapped_column(String(length=16))
    applied_state: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        server_default=text("'absent'"),
    )
    status: Mapped[str] = mapped_column(String(length=16), server_default=text("'pending'"), nullable=False)
    last_error: Mapped[str] = mapped_column(nullable=True)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    op_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    key: Mapped[VpnKey] = relationship(back_populates="assignments")
    node: Mapped[VpnNode] = relationship(back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("key_id", "node_id", name="uq_key_node"),
        Index("ix_key_assignment_node_id", "node_id"),
        Index("ix_key_assignment_key_id", "key_id"),
        Index("ix_key_assignment_status", "status"),
        Index("ix_key_assignment_next_retry_at", "next_retry_at"),
    )
