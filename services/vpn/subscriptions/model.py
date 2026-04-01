from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, String, ForeignKey, Index, DateTime, Boolean, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.base_model import Base


class Subscription(Base):
    __tablename__ = "subscription"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("plan.id"), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    prev_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    prev_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    profile_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_region: Mapped[str | None] = mapped_column(String(16), nullable=True)
    root_vpn_key_id: Mapped[UUID | None] = mapped_column(ForeignKey("vpn_key.id"), nullable=True)
    hwid_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_devices: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_device_slots: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    used_traffic_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0"),
    )
    lifetime_used_traffic_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0"),
    )
    last_traffic_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    plan: Mapped["Plan"] = relationship(lazy="joined")
    devices: Mapped[list["SubscriptionDevice"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_subscription_user_id", "user_id"),
        Index("ix_subscription_plan_id", "plan_id"),
        Index("ix_subscription_token_hash", "token_hash"),
        Index("ix_subscription_prev_token_hash", "prev_token_hash"),
    )


class SubscriptionDevice(Base):
    __tablename__ = "subscription_device"

    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("subscription.id", ondelete="CASCADE"),
        nullable=False,
    )
    hwid_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    subscription: Mapped["Subscription"] = relationship(back_populates="devices")
    device_keys: Mapped[list["SubscriptionDeviceKey"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("subscription_id", "hwid_hash", name="uq_subscription_device_hwid"),
        Index("ix_subscription_device_subscription_id", "subscription_id"),
    )


class SubscriptionDeviceKey(Base):
    __tablename__ = "subscription_device_key"

    subscription_device_id: Mapped[UUID] = mapped_column(
        ForeignKey("subscription_device.id", ondelete="CASCADE"),
        nullable=False,
    )
    vpn_key_id: Mapped[UUID] = mapped_column(
        ForeignKey("vpn_key.id", ondelete="CASCADE"),
        nullable=False,
    )
    transport: Mapped[str] = mapped_column(String(16), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    device: Mapped["SubscriptionDevice"] = relationship(back_populates="device_keys")

    __table_args__ = (
        UniqueConstraint(
            "subscription_device_id",
            "vpn_key_id",
            name="uq_subscription_device_key_device_key",
        ),
        UniqueConstraint(
            "subscription_device_id",
            "transport",
            name="uq_subscription_device_key_device_transport",
        ),
        Index("ix_subscription_device_key_device_id", "subscription_device_id"),
        Index("ix_subscription_device_key_vpn_key_id", "vpn_key_id"),
        Index("ix_subscription_device_key_transport", "transport"),
    )
