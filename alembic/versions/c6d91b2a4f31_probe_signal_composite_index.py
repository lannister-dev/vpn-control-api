"""probe signal composite index

Revision ID: c6d91b2a4f31
Revises: b1f7d9c3e4a2
Create Date: 2026-02-17

"""

from alembic import op


revision = "c6d91b2a4f31"
down_revision = "b1f7d9c3e4a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_probe_signal_node_source_checked_at",
        "probe_signal",
        ["node_id", "source", "checked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_probe_signal_node_source_checked_at", table_name="probe_signal")
