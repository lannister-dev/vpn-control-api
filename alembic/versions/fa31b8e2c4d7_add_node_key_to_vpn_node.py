"""add node_key to vpn_node for explicit bootstrap identity

Revision ID: fa31b8e2c4d7
Revises: f9a2d7c4b5e1
Create Date: 2026-02-26
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa31b8e2c4d7"
down_revision: Union[str, None] = "f9a2d7c4b5e1"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column("vpn_node", sa.Column("node_key", sa.String(length=128), nullable=True))
    op.create_index("ix_vpn_node_node_key", "vpn_node", ["node_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_vpn_node_node_key", table_name="vpn_node")
    op.drop_column("vpn_node", "node_key")
