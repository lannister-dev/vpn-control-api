"""add role to vpn_node

Revision ID: 9c41e5d7a6b2
Revises: 8b1f5a7e2d11
Create Date: 2026-02-16

"""

from alembic import op
import sqlalchemy as sa


revision = "9c41e5d7a6b2"
down_revision = "8b1f5a7e2d11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vpn_node",
        sa.Column(
            "role",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'backend'"),
        ),
    )
    op.create_index("ix_vpn_node_role", "vpn_node", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vpn_node_role", table_name="vpn_node")
    op.drop_column("vpn_node", "role")
