"""add zone column to vpn_node for geographical grouping of entry↔backend

Revision ID: d7f3a9b5c8e1
Revises: f2a3b4c5d6e7
Create Date: 2026-04-20
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "d7f3a9b5c8e1"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("vpn_node")}
    if "zone" not in columns:
        op.add_column(
            "vpn_node",
            sa.Column("zone", sa.String(length=32), nullable=True),
        )
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("vpn_node")}
    if "ix_vpn_node_zone" not in existing_indexes:
        op.create_index(
            "ix_vpn_node_zone",
            "vpn_node",
            ["zone"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("vpn_node")}
    if "ix_vpn_node_zone" in existing_indexes:
        op.drop_index("ix_vpn_node_zone", table_name="vpn_node")
    columns = {col["name"] for col in inspector.get_columns("vpn_node")}
    if "zone" in columns:
        op.drop_column("vpn_node", "zone")
