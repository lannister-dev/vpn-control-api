from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.zones.models import Zone
from shared.database.base_model import Base


class VpnNode(Base):
    __tablename__ = "vpn_node"

    name: Mapped[str] = mapped_column(String(length=64), unique=True)
    role: Mapped[str] = mapped_column(String(length=16), nullable=False, server_default=text("'backend'"), index=True)
    region: Mapped[str] = mapped_column(String(length=32))  # de, nl, fi
    public_domain: Mapped[str] = mapped_column(String(length=255))
    reality_ip: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    internal_wg_ip: Mapped[str] = mapped_column(String(length=64))  # 10.0.1.x
    node_key: Mapped[str | None] = mapped_column(String(length=128), unique=True, nullable=True, index=True)
    xray_api_port: Mapped[int] = mapped_column(Integer, default=10085)
    auth_token_hash: Mapped[str] = mapped_column(String(length=64), nullable=False, index=True)
    agent_port: Mapped[int] = mapped_column(Integer, default=9000)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    is_draining: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    drain_source: Mapped[str | None] = mapped_column(String(length=16), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=100, server_default=text("100"), nullable=False)
    zone: Mapped[str | None] = mapped_column(
        String(length=32),
        ForeignKey("zone.code", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    zone_ref: Mapped["Zone | None"] = relationship(
        lazy="joined",
        foreign_keys="VpnNode.zone",
        primaryjoin="VpnNode.zone == Zone.code",
    )
    upstream_node_id: Mapped[UUID | None] = mapped_column(ForeignKey("vpn_node.id"), nullable=True, index=True)
    bootstrap_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bootstrapped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    wg_public_key: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    wg_listen_port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    assignments: Mapped[list["KeyAssignment"]] = relationship(back_populates="node")
    agent_state: Mapped["NodeAgentState"] = relationship(back_populates="node")
    agent_identities: Mapped[list["NodeAgentIdentity"]] = relationship(back_populates="node")


class NodeAgentState(Base):
    __tablename__ = "node_agent_state"

    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), unique=True)
    agent_version: Mapped[str] = mapped_column(String(length=32), nullable=False)
    last_config_version: Mapped[int] = mapped_column(default=0)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    is_healthy: Mapped[bool] = mapped_column(default=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


    node: Mapped["VpnNode"] = relationship(back_populates="agent_state")


class NodeAgentIdentity(Base):
    __tablename__ = "node_agent_identity"

    node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_node.id"), nullable=False, index=True)
    agent_instance_id: Mapped[UUID] = mapped_column(nullable=False)
    auth_token_hash: Mapped[str] = mapped_column(String(length=64), nullable=False)
    prev_auth_token_hash: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    prev_auth_token_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_resync_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    last_bootstrap_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    node: Mapped["VpnNode"] = relationship(back_populates="agent_identities")

    __table_args__ = (
        UniqueConstraint(
            "node_id", "agent_instance_id", name="uq_node_agent_identity_node_agent"),
    )
