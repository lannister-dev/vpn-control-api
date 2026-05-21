"""add vpn_node.is_virtual

Revision ID: a7b9d3e5f8c1
Revises: c8e2b1d4f7a3
"""

import sqlalchemy as sa

from alembic import op

revision = "a7b9d3e5f8c1"
down_revision = "c8e2b1d4f7a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vpn_node",
        sa.Column(
            "is_virtual",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("vpn_node", "is_virtual")
