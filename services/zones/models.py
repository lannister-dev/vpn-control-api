from sqlalchemy import Integer, String, text
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
