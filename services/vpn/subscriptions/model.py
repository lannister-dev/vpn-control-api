from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import String, ForeignKey, Index, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.base_model import Base


class Subscription(Base):
    __tablename__ = "subscription"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(nullable=False, default=uuid4, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    prev_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    prev_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    profile_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_region: Mapped[str | None] = mapped_column(String(16), nullable=True)

    user: Mapped["User"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        Index("ix_subscription_user_id", "user_id"),
        Index("ix_subscription_token_hash", "token_hash"),
        Index("ix_subscription_prev_token_hash", "prev_token_hash")
    )