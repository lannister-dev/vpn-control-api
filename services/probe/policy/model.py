from sqlalchemy import Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class ProbePolicy(Base):
    __tablename__ = "probe_policy"

    route_suspected_after_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    route_degraded_after_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    route_block_after_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4"))
    route_block_cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))

    auto_drain_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    auto_drain_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    auto_drain_min_consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    auto_drain_max_probe_age_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("600"))
    auto_drain_max_nodes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("20"))

    auto_undrain_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    auto_undrain_min_consecutive_successes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    auto_undrain_max_probe_age_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("600"))
