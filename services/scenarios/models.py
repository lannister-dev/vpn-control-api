from datetime import datetime
from uuid import UUID

from sqlalchemy import (
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


class ScenarioCampaign(Base):
    __tablename__ = "scenario_campaign"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_event: Mapped[str | None] = mapped_column(String(48), nullable=True)
    entry_node_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    nodes: Mapped[list["ScenarioNode"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list["ScenarioEdge"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class ScenarioNode(Base):
    __tablename__ = "scenario_node"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_campaign.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)
    pos_cx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    pos_top: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    condition: Mapped[str] = mapped_column(
        String(32), nullable=False, default="always", server_default=text("'always'")
    )
    repeat_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    repeat_interval_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    inline_buttons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    media_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    check_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)

    conversion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    campaign: Mapped["ScenarioCampaign"] = relationship(back_populates="nodes")

    __table_args__ = (
        UniqueConstraint("campaign_id", "node_key", name="uq_scenario_node_campaign_key"),
    )


class ScenarioEdge(Base):
    __tablename__ = "scenario_edge"

    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_campaign.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_key: Mapped[str] = mapped_column(String(64), nullable=False)
    to_key: Mapped[str] = mapped_column(String(64), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(8), nullable=True)

    campaign: Mapped["ScenarioCampaign"] = relationship(back_populates="edges")

    __table_args__ = (
        Index("ix_scenario_edge_campaign_from", "campaign_id", "from_key"),
    )


class ScenarioState(Base):
    __tablename__ = "scenario_state"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scenario_campaign.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_node_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node_sends: Mapped[int] = mapped_column(
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
        UniqueConstraint("user_id", "campaign_id", name="uq_scenario_state_user_campaign"),
        Index("ix_scenario_state_due", "status", "next_send_at"),
    )
