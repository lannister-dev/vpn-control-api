from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class ProbePolicy(Base):
    __tablename__ = "probe_policy"

    auto_route_health_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))

    route_suspected_after_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    route_degraded_after_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    route_block_after_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4"))
    route_block_cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))

    auto_drain_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    auto_drain_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    auto_drain_min_consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    auto_drain_max_probe_age_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("600"))
    auto_drain_max_nodes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("20"))
    auto_drain_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auto_drain_require_recent_failure: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    auto_drain_include_already_draining: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    auto_drain_target_backend_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vpn_node.id", ondelete="SET NULL"), nullable=True,
    )
    auto_drain_last_migration_reason: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'probe_auto_failure'"),
    )

    auto_undrain_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    auto_undrain_min_consecutive_successes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    auto_undrain_max_probe_age_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("600"))
    auto_undrain_source: Mapped[str | None] = mapped_column(String(64), nullable=True)

    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    cleanup_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    cleanup_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3600"))

    synthetic_reconcile_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    synthetic_reconcile_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("300"))
    synthetic_key_valid_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3650"))
    synthetic_key_traffic_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("102400"))
