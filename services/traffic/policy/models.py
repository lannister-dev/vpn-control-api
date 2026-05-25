from sqlalchemy import Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class TrafficPolicy(Base):
    __tablename__ = "traffic_policy"

    user_cleanup_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    user_cleanup_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3600"))
    user_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("35"))

    node_cleanup_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    node_cleanup_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3600"))
    node_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
