"""add probe signal table

Revision ID: b1f7d9c3e4a2
Revises: f7b3c4d9e210
Create Date: 2026-02-17

"""

from alembic import op
import sqlalchemy as sa


revision = "b1f7d9c3e4a2"
down_revision = "f7b3c4d9e210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "probe_signal",
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("is_reachable", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["vpn_node.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_probe_signal_node_id", "probe_signal", ["node_id"], unique=False)
    op.create_index("ix_probe_signal_source", "probe_signal", ["source"], unique=False)
    op.create_index("ix_probe_signal_checked_at", "probe_signal", ["checked_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_probe_signal_checked_at", table_name="probe_signal")
    op.drop_index("ix_probe_signal_source", table_name="probe_signal")
    op.drop_index("ix_probe_signal_node_id", table_name="probe_signal")
    op.drop_table("probe_signal")

