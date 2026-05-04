"""vpn_node WG-mesh fields

Adds wg_public_key + wg_listen_port columns to vpn_node. node-agent calls
the WG bootstrap endpoint with its generated public key; control-api stores
it and returns the assigned internal_wg_ip.

Revision ID: f4b6c8d2a3e7
Revises: e9f2c4a6b8d1
Create Date: 2026-05-04
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "f4b6c8d2a3e7"
down_revision: Union[str, None] = "e9f2c4a6b8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vpn_node",
        sa.Column("wg_public_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "vpn_node",
        sa.Column("wg_listen_port", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vpn_node", "wg_listen_port")
    op.drop_column("vpn_node", "wg_public_key")
