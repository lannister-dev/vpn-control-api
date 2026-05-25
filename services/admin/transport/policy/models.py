from sqlalchemy import Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class TransportPolicy(Base):
    __tablename__ = "transport_policy"

    cleanup_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    cleanup_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3600"))
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
