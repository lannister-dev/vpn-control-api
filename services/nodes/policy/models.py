from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class NodePolicy(Base):
    __tablename__ = "node_policy"

    # freshness / staleness
    stale_after_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
    heartbeat_unhealthy_drain_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    heartbeat_healthy_undrain_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))

    # backend auto-heal (drain stale backends + migrate placements)
    auto_heal_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    auto_heal_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("60"))
    auto_heal_max_nodes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("20"))
    auto_heal_drain_cooldown_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("180"))
    auto_undrain_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))

    # placement error-retry reconciler
    placement_error_retry_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    placement_error_retry_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    placement_error_retry_after_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))

    # placement rebalance reconciler (moves placements off stale backends)
    placement_rebalance_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    placement_rebalance_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    placement_rebalance_batch_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("200"))

    # entry pool drain
    entry_apply_fail_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    entry_apply_fail_unhealthy: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    entry_auto_drain_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    entry_auto_drain_tick_sec: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("60"))
    entry_auto_drain_probe_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    entry_auto_drain_max_nodes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))
    entry_auto_drain_reason: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'entry_auto_drain'"),
    )
    entry_auto_undrain_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    entry_auto_undrain_healthy_ticks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
