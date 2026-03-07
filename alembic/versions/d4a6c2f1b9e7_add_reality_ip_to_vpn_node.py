"""add vpn_node.reality_ip column for Reality transport host

Revision ID: d4a6c2f1b9e7
Revises: c8f1e2d3a4b5
Create Date: 2026-02-28
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4a6c2f1b9e7"
down_revision: Union[str, None] = "c8f1e2d3a4b5"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vpn_node",
        sa.Column("reality_ip", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vpn_node", "reality_ip")
