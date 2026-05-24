from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class AdminAuditRecord(Base):
    __tablename__ = "admin_audit_log"

    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        Index("ix_admin_audit_created_at", "created_at"),
        Index("ix_admin_audit_action", "action"),
        Index("ix_admin_audit_actor", "actor"),
    )
