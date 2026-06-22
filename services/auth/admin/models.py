from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class AdminUser(Base):
    __tablename__ = "admin_user"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(nullable=True, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    ui_prefs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class AdminSession(Base):
    __tablename__ = "admin_session"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_event"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
