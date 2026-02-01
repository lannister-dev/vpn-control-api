from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON
from sqlalchemy.orm import mapped_column, Mapped, relationship

from shared.database.base_model import Base


class VpnNode(Base):
    __tablename__ = "vpn_node"

    name: Mapped[str] = mapped_column(String(length=64), unique=True)
    region: Mapped[str] = mapped_column(String(length=32))  # de, nl, fi
    public_domain: Mapped[str] = mapped_column(String(length=255))
    internal_wg_ip: Mapped[str] = mapped_column(String(length=64))  # 10.0.1.x
    xray_api_port: Mapped[int] = mapped_column(Integer, default=10085)
    auth_token_hash: Mapped[str] = mapped_column(String(length=64), nullable=False, index=True)
    agent_port: Mapped[int] = mapped_column(Integer, default=9000)

    assignments: Mapped[list["KeyAssignment"]] = relationship(back_populates="node")
    agent_state: Mapped["NodeAgentState"] = relationship(back_populates="node")


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
