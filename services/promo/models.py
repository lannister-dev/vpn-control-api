import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class PromoCode(Base):
    __tablename__ = "promo_code"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    discount_type: Mapped[str] = mapped_column(String(8), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    max_discount_rub: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    audience: Mapped[str] = mapped_column(
        String(20), default="all", server_default=text("'all'"), nullable=False
    )
    plan_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    applies_to: Mapped[str] = mapped_column(
        String(16), default="any", server_default=text("'any'"), nullable=False
    )
    min_amount_rub: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    max_activations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_per_user: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activation_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_user.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_promo_code_code", "code"),
        Index("ix_promo_code_is_active", "is_active"),
    )


class PromoActivation(Base):
    __tablename__ = "promo_activation"

    promo_code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("promo_code.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_order.id", ondelete="SET NULL"), nullable=True
    )
    amount_before: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_applied: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    amount_after: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    __table_args__ = (
        Index("ix_promo_activation_promo_code_id", "promo_code_id"),
        Index("ix_promo_activation_user_id", "user_id"),
        Index("ix_promo_activation_promo_user", "promo_code_id", "user_id"),
    )
