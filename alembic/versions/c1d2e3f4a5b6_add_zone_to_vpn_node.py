"""add zone column to vpn_node for geographical grouping of entry↔backend

Revision ID: c1d2e3f4a5b6
Revises: f2a3b4c5d6e7
Create Date: 2026-04-20
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vpn_node",
        sa.Column("zone", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_vpn_node_zone",
        "vpn_node",
        ["zone"],
    )


def downgrade() -> None:
    op.drop_index("ix_vpn_node_zone", table_name="vpn_node")
    op.drop_column("vpn_node", "zone")
