from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped, relationship

from shared.database.base_model import Base


class VpnKey(Base):
    __tablename__ = "vpn_key"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"))
    protocol: Mapped[str] = mapped_column(String(length=16))  # vless
    transport: Mapped[str] = mapped_column(String(length=16))  # ws / xhttp
    xray_user_id: Mapped[str] = mapped_column(String(length=36), unique=True)
    valid_until: Mapped[datetime]
    traffic_limit_mb: Mapped[int] = mapped_column(nullable=False)
    is_revoked: Mapped[bool] = mapped_column(default=False)

    user: Mapped["User"] = relationship(back_populates="keys")
    assignments: Mapped[list["KeyAssignment"]] = relationship(
        back_populates="key",
        cascade="all, delete-orphan"
    )


class KeyAssignment(Base):
    __tablename__ = "key_assignment"

    key_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_key.id"))
    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"))
    desired_state: Mapped[str] = mapped_column(String(length=16))
    applied_state: Mapped[str] = mapped_column(String(length=16))
    status: Mapped[str] = mapped_column(String(length=16), default="pending")
    last_error: Mapped[str] = mapped_column(nullable=True)
    last_applied_at: Mapped[datetime | None]

    key: Mapped["VpnKey"] = relationship(back_populates="assignments")
    node: Mapped["VpnNode"] = relationship(back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("key_id", "node_id", name="uq_key_node"),
    )
