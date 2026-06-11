"""add broadcast.attempts for scheduled-broadcast retry

Revision ID: c3f7a1b9e204
Revises: b7c1e0a9f342
Create Date: 2026-06-11

"""

import sqlalchemy as sa

from alembic import op

revision = "c3f7a1b9e204"
down_revision = "b7c1e0a9f342"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "broadcast",
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("broadcast", "attempts")
