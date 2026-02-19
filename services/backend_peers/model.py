from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class BackendPeer(Base):
    __tablename__ = "backend_peer"

    backend_node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False)
    gateway_node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False)

    internal_uuid: Mapped[str] = mapped_column(String(length=36), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
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
    last_error: Mapped[str | None] = mapped_column(String(length=255), nullable=True)

    __table_args__ = (
        UniqueConstraint("backend_node_id", "gateway_node_id", name="uq_backend_peer_pair"),
        CheckConstraint("op_version >= 1", name="ck_backend_peer_op_version_ge_1"),
        CheckConstraint("applied_version >= 0", name="ck_backend_peer_applied_version_ge_0"),
        CheckConstraint("applied_version <= op_version", name="ck_backend_peer_applied_version_lte_op"),
        Index("ix_backend_peer_backend_node_id", "backend_node_id"),
        Index("ix_backend_peer_gateway_node_id", "gateway_node_id"),
        Index("ix_backend_peer_status", "status"),
        Index("ix_backend_peer_applied_state", "applied_state"),
    )
