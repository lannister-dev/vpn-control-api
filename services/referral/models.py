from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BIGINT, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class Referral(Base):
    __tablename__ = "referral"

    referrer_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    referred_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    referred_reward_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("referred_user_id", name="uq_referral_referred_user"),
        Index("ix_referral_referrer_user_id", "referrer_user_id"),
        Index("ix_referral_status", "status"),
    )
