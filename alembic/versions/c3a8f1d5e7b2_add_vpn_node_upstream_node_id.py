"""add vpn_node upstream_node_id

Revision ID: c3a8f1d5e7b2
Revises: d46f956272de
Create Date: 2026-03-25 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a8f1d5e7b2'
down_revision: Union[str, None] = 'd46f956272de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vpn_node",
        sa.Column("upstream_node_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_vpn_node_upstream_node_id",
        "vpn_node",
        "vpn_node",
        ["upstream_node_id"],
        ["id"],
    )
    op.create_index(
        "ix_vpn_node_upstream_node_id",
        "vpn_node",
        ["upstream_node_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vpn_node_upstream_node_id", table_name="vpn_node")
    op.drop_constraint("fk_vpn_node_upstream_node_id", "vpn_node", type_="foreignkey")
    op.drop_column("vpn_node", "upstream_node_id")
