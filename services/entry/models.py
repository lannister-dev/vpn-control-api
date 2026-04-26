from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class EntryBackendAssignment(Base):
    __tablename__ = "entry_backend_assignment"

    entry_node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False, index=True)
    backend_node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False, index=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    rank: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), index=True)

    __table_args__ = (
        UniqueConstraint(
            "entry_node_id",
            "backend_node_id",
            name="uq_entry_backend_assignment_entry_backend",
        ),
    )
