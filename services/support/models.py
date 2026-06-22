from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.base_model import Base


class SupportTicket(Base):
    __tablename__ = "support_ticket"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), default="new", server_default=text("'new'"), nullable=False
    )
    priority: Mapped[str] = mapped_column(
        String(10), default="normal", server_default=text("'normal'"), nullable=False
    )
    category: Mapped[str] = mapped_column(
        String(20), default="other", server_default=text("'other'"), nullable=False
    )
    assignee_admin_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("admin_user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.utcnow(),
        nullable=False,
        index=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_user_msg_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_support_ticket_status_activity", "status", "last_activity_at"),
    )


class SupportMessage(Base):
    __tablename__ = "support_message"

    ticket_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("support_ticket.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    sender_admin_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("admin_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_note: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    delivered: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class SupportAttachment(Base):
    __tablename__ = "support_attachment"

    message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("support_message.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    tg_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    tg_file_unique_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SupportTemplate(Base):
    __tablename__ = "support_template"

    tag: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    used_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )


class Broadcast(Base):
    __tablename__ = "broadcast"

    audience: Mapped[str] = mapped_column(String(20), nullable=False)
    audience_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    plan_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plan.id", ondelete="SET NULL"),
        nullable=True,
    )
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    media_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    inline_buttons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    entities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    custom_emoji_assets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="draft", server_default=text("'draft'"), nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    errors: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    clicks: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    target_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    promo_code_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("promo_code.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_admin_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("admin_user.id", ondelete="SET NULL"),
        nullable=True,
    )


class RecurringBroadcastSchedule(Base):
    __tablename__ = "recurring_broadcast_schedule"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    audience: Mapped[str] = mapped_column(String(20), nullable=False)
    plan_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("plan.id", ondelete="SET NULL"), nullable=True
    )
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    media_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    inline_buttons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    promo_code_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("promo_code.id", ondelete="SET NULL"),
        nullable=True,
    )
    cadence: Mapped[str] = mapped_column(
        String(8), default="daily", server_default=text("'daily'"), nullable=False
    )
    time_of_day: Mapped[str] = mapped_column(String(5), nullable=False)
    weekdays: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_admin_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("admin_user.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_recurring_broadcast_next_run_at", "next_run_at"),
    )


class BroadcastLog(Base):
    __tablename__ = "broadcast_log"

    broadcast_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("broadcast.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    delivered: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    clicked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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
        PGUUID(as_uuid=True),
        ForeignKey("drip_campaign.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    condition: Mapped[str] = mapped_column(
        String(32), nullable=False, default="always", server_default=text("'always'")
    )
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
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
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("drip_campaign.id", ondelete="CASCADE"),
        nullable=False,
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
