"""add node_traffic_usage

Per-(entry,backend) time-bucketed traffic counters. Rows are emitted by
node-agents from HAProxy `show stat` deltas every ~30 seconds. Admin
aggregates SUM over created_at windows.

Revision ID: e1b2c3d4f5a6
Revises: d9e1f2a3b4c5
Create Date: 2026-04-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e1b2c3d4f5a6"
down_revision: Union[str, Sequence[str], None] = "d9e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "node_traffic_usage",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("entry_node_id", sa.UUID(), nullable=False),
        sa.Column("backend_node_id", sa.UUID(), nullable=True),
        sa.Column("bytes_in", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("bytes_out", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("active_sessions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_sessions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["entry_node_id"], ["vpn_node.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["backend_node_id"], ["vpn_node.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_node_traffic_entry_created",
        "node_traffic_usage",
        ["entry_node_id", "created_at"],
    )
    op.create_index(
        "ix_node_traffic_backend_created",
        "node_traffic_usage",
        ["backend_node_id", "created_at"],
    )
    op.create_index(
        "ix_node_traffic_created_at",
        "node_traffic_usage",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_node_traffic_created_at", table_name="node_traffic_usage")
    op.drop_index("ix_node_traffic_backend_created", table_name="node_traffic_usage")
    op.drop_index("ix_node_traffic_entry_created", table_name="node_traffic_usage")
    op.drop_table("node_traffic_usage")
