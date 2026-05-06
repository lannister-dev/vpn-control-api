"""vpn_node.drain_source

Marks origin of drain ('admin' = admin set it; 'auto_heal' = auto-heal set
it; null = not draining). Auto-heal must not undrain admin-drained nodes.

Revision ID: d2a8c5e7f3b1
Revises: f4b6c8d2a3e7
Create Date: 2026-05-05
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "d2a8c5e7f3b1"
down_revision: Union[str, None] = "f4b6c8d2a3e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vpn_node",
        sa.Column("drain_source", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vpn_node", "drain_source")
