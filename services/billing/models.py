import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class PaymentOrder(Base):
    __tablename__ = "payment_order"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plan.id", ondelete="SET NULL"), nullable=True
    )
    amount_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default=text("'pending'"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    payment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_meta: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscription.id", ondelete="SET NULL"), nullable=True
    )
    order_type: Mapped[str] = mapped_column(
        String(24), default="plan_purchase", server_default=text("'plan_purchase'"), nullable=False
    )
    device_slots_qty: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    period_months: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )

    __table_args__ = (
        Index("ix_payment_order_user_id", "user_id"),
        Index("ix_payment_order_status", "status"),
        Index("ix_payment_order_provider", "provider"),
        Index("ix_payment_order_expires_at", "expires_at"),
        Index("ix_payment_order_order_type", "order_type"),
    )


class BalanceTransaction(Base):
    __tablename__ = "balance_transaction"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_order.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_balance_transaction_user_id", "user_id"),
        Index("ix_balance_transaction_type", "type"),
        Index("ix_balance_transaction_created_at", "created_at"),
    )
