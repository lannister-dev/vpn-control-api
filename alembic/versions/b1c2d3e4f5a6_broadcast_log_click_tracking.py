"""add click tracking to broadcast_log

Revision ID: b1c2d3e4f5a6
Revises: e2b6d9a4c108
Create Date: 2026-06-16

"""

import sqlalchemy as sa

from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "e2b6d9a4c108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "broadcast_log",
        sa.Column(
            "clicked",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "broadcast_log",
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("broadcast_log", "clicked_at")
    op.drop_column("broadcast_log", "clicked")
