"""add key_node_traffic_counter table for per-node delta tracking

Revision ID: a1c2d3e4f5b6
Revises: c3d4e5f6a7b8
Create Date: 2026-03-21

"""

import sqlalchemy as sa

from alembic import op

revision = "a1c2d3e4f5b6"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "key_node_traffic_counter",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("vpn_key.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("last_reported_total_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id", "node_id", name="uq_key_node_traffic_counter"),
    )
    op.create_index("ix_key_node_traffic_counter_key_id", "key_node_traffic_counter", ["key_id"])


def downgrade() -> None:
    op.drop_index("ix_key_node_traffic_counter_key_id", table_name="key_node_traffic_counter")
    op.drop_table("key_node_traffic_counter")
