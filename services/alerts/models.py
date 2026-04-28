from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class AlertEvent(Base):
    __tablename__ = "alert_events"

    level: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_alert_events_created_at", "created_at"),
        Index("ix_alert_events_level", "level"),
        Index("ix_alert_events_source", "source"),
    )
