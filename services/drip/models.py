from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.base_model import Base


class DripCampaign(Base):
    __tablename__ = "drip_campaign"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_event: Mapped[str | None] = mapped_column(String(48), nullable=True)

    steps: Mapped[list["DripStep"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="DripStep.step_order",
    )


class DripStep(Base):
    __tablename__ = "drip_step"

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("drip_campaign.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    condition: Mapped[str] = mapped_column(
        String(32), nullable=False, default="always", server_default=text("'always'")
    )
    text_body: Mapped[str] = mapped_column(nullable=False)
    inline_buttons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    media_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    campaign: Mapped["DripCampaign"] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("campaign_id", "step_order", name="uq_drip_step_campaign_order"),
    )


class UserCampaignState(Base):
    __tablename__ = "user_campaign_state"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("drip_campaign.id", ondelete="CASCADE"), nullable=False
    )
    current_step: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_send_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_step_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "campaign_id", name="uq_user_campaign"),
        Index("ix_user_campaign_due", "status", "next_send_at"),
    )
