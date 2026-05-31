from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, text
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
    entry_routing_override_backend_tag: Mapped[str | None] = mapped_column(
        String(length=128), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="keys")
    subscription: Mapped[Subscription] = relationship(
        foreign_keys=[subscription_id], lazy="select",
    )
    __table_args__ = (
        Index("ix_vpn_key_user_id", "user_id"),
        Index("ix_vpn_key_valid_until", "valid_until"),
        Index("ix_vpn_key_is_revoked", "is_revoked"),
        Index("ix_vpn_key_subscription_id", "subscription_id"),
    )
