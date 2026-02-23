"""add routes and transport profiles

Revision ID: a4d8e7c91f20
Revises: c6d91b2a4f31
Create Date: 2026-02-19 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4d8e7c91f20"
down_revision: Union[str, None] = "c6d91b2a4f31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transport_profile",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("protocol", sa.String(length=16), server_default=sa.text("'vless'"), nullable=False),
        sa.Column("network", sa.String(length=16), server_default=sa.text("'tcp'"), nullable=False),
        sa.Column("security", sa.String(length=16), server_default=sa.text("'reality'"), nullable=False),
        sa.Column("flow", sa.String(length=64), nullable=True),
        sa.Column("reality_public_key", sa.String(length=128), nullable=True),
        sa.Column("reality_short_id", sa.String(length=32), nullable=True),
        sa.Column("reality_server_name", sa.String(length=255), nullable=True),
        sa.Column("tls_fingerprint", sa.String(length=64), server_default=sa.text("'chrome'"), nullable=False),
        sa.Column("grpc_service_name", sa.String(length=64), nullable=True),
        sa.Column("port", sa.Integer(), server_default=sa.text("443"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("port >= 1 AND port <= 65535", name="ck_transport_profile_port_range"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_transport_profile_name", "transport_profile", ["name"], unique=False)
    op.create_index("ix_transport_profile_network", "transport_profile", ["network"], unique=False)
    op.create_index("ix_transport_profile_security", "transport_profile", ["security"], unique=False)

    op.create_table(
        "route",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("transport_profile_id", sa.UUID(), nullable=False),
        sa.Column("health_status", sa.String(length=16), server_default=sa.text("'healthy'"), nullable=False),
        sa.Column("base_weight", sa.Integer(), server_default=sa.text("50"), nullable=False),
        sa.Column("effective_weight", sa.Integer(), server_default=sa.text("50"), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warmup_stage", sa.Integer(), nullable=True),
        sa.Column("warmup_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("base_weight >= 0", name="ck_route_base_weight_ge_0"),
        sa.CheckConstraint("effective_weight >= 0", name="ck_route_effective_weight_ge_0"),
        sa.CheckConstraint("effective_weight <= base_weight", name="ck_route_effective_weight_lte_base_weight"),
        sa.ForeignKeyConstraint(["node_id"], ["vpn_node.id"]),
        sa.ForeignKeyConstraint(["transport_profile_id"], ["transport_profile.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_route_node_id", "route", ["node_id"], unique=False)
    op.create_index("ix_route_transport_profile_id", "route", ["transport_profile_id"], unique=False)
    op.create_index("ix_route_health_status", "route", ["health_status"], unique=False)
    op.create_index("ix_route_effective_weight", "route", ["effective_weight"], unique=False)
    op.create_index("ix_route_cooldown_until", "route", ["cooldown_until"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_route_cooldown_until", table_name="route")
    op.drop_index("ix_route_effective_weight", table_name="route")
    op.drop_index("ix_route_health_status", table_name="route")
    op.drop_index("ix_route_transport_profile_id", table_name="route")
    op.drop_index("ix_route_node_id", table_name="route")
    op.drop_table("route")

    op.drop_index("ix_transport_profile_security", table_name="transport_profile")
    op.drop_index("ix_transport_profile_network", table_name="transport_profile")
    op.drop_index("ix_transport_profile_name", table_name="transport_profile")
    op.drop_table("transport_profile")
