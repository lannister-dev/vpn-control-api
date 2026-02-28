from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class UserPlacement(Base):
    __tablename__ = "user_placement"

    key_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_key.id"), nullable=False)
    backend_node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False)

    desired_state: Mapped[str] = mapped_column(
        String(length=20),
        nullable=False,
        server_default=text("'active'"),
    )
    applied_state: Mapped[str] = mapped_column(
        String(length=20),
        nullable=False,
        server_default=text("'pending'"),
    )
    op_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    applied_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    sticky_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_migration_reason: Mapped[str | None] = mapped_column(String(length=64), nullable=True)

    __table_args__ = (
        UniqueConstraint("key_id", "backend_node_id", name="uq_user_placement_key_backend"),
        CheckConstraint("op_version >= 1", name="ck_user_placement_op_version_ge_1"),
        CheckConstraint("applied_version >= 0", name="ck_user_placement_applied_version_ge_0"),
        CheckConstraint("applied_version <= op_version", name="ck_user_placement_applied_version_lte_op"),
        Index("ix_user_placement_key_id", "key_id"),
        Index("ix_user_placement_backend_node_id", "backend_node_id"),
        Index(
            "ix_user_placement_backend_node_op_version_id_active",
            "backend_node_id",
            "op_version",
            "id",
            postgresql_where=text("is_active = true"),
        ),
        Index("ix_user_placement_desired_state", "desired_state"),
        Index("ix_user_placement_applied_state", "applied_state"),
    )
