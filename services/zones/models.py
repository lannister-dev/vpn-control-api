from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class Zone(Base):
    __tablename__ = "zone"

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("''"))
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Whitelist (or any other) entry node that becomes urltest fallback in client
    # config when the zone's primary entry is unreachable (DPI/down).
    fallback_entry_node_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vpn_node.id", ondelete="SET NULL"),
        nullable=True,
    )
