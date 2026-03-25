from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class TransportProfile(Base):
    __tablename__ = "transport_profile"

    name: Mapped[str] = mapped_column(String(length=100), nullable=False, unique=True)
    protocol: Mapped[str] = mapped_column(String(length=16), nullable=False, server_default=text("'vless'"))
    network: Mapped[str] = mapped_column(String(length=16), nullable=False, server_default=text("'tcp'"))
    security: Mapped[str] = mapped_column(String(length=16), nullable=False, server_default=text("'reality'"))
    flow: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    reality_public_key: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    reality_short_id: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    reality_server_name: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    tls_fingerprint: Mapped[str] = mapped_column(String(length=64), nullable=False, server_default=text("'chrome'"))
    grpc_service_name: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    port: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("443"))

    __table_args__ = (
        CheckConstraint("port >= 1 AND port <= 65535", name="ck_transport_profile_port_range"),
        Index("ix_transport_profile_name", "name"),
        Index("ix_transport_profile_security", "security"),
        Index("ix_transport_profile_network", "network"),
    )


class Route(Base):
    __tablename__ = "route"

    name: Mapped[str] = mapped_column(String(length=100), nullable=False, unique=True)
    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False)
    entry_node_id: Mapped[UUID | None] = mapped_column(ForeignKey("vpn_node.id"), nullable=True)
    transport_profile_id: Mapped[UUID] = mapped_column(ForeignKey("transport_profile.id"), nullable=False)
    health_status: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        server_default=text("'healthy'"),
    )
    base_weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))
    effective_weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warmup_stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warmup_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("base_weight >= 0", name="ck_route_base_weight_ge_0"),
        CheckConstraint("effective_weight >= 0", name="ck_route_effective_weight_ge_0"),
        CheckConstraint("effective_weight <= base_weight", name="ck_route_effective_weight_lte_base_weight"),
        Index("ix_route_node_id", "node_id"),
        Index("ix_route_entry_node_id", "entry_node_id"),
        Index("ix_route_transport_profile_id", "transport_profile_id"),
        Index("ix_route_health_status", "health_status"),
        Index("ix_route_effective_weight", "effective_weight"),
        Index("ix_route_cooldown_until", "cooldown_until"),
    )
