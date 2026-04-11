from datetime import datetime
from decimal import Decimal

from sqlalchemy import BIGINT, DateTime, Index, Numeric, String
from sqlalchemy.orm import mapped_column, Mapped, relationship

from services.vpn.subscriptions.model import Subscription
from shared.database.base_model import Base


class User(Base):
    __tablename__ = "user"

    telegram_id: Mapped[int] = mapped_column(BIGINT, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(nullable=True)
    terms_accepted: Mapped[bool] = mapped_column(default=False, nullable=False)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referral_code: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)

    __table_args__ = (
        Index("ix_user_referral_code", "referral_code", unique=True),
    )

    keys: Mapped[list["VpnKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
