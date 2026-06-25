"""drip repeating step: repeat_count/interval on node + node_sends on state

Revision ID: d7c4a1e9f0b2
Revises: a3f9c2e1b7d4
Create Date: 2026-06-25
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "d7c4a1e9f0b2"
down_revision: Union[str, None] = "a3f9c2e1b7d4"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "drip_node",
        sa.Column("repeat_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "drip_node",
        sa.Column("repeat_interval_sec", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "user_campaign_state",
        sa.Column("node_sends", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("user_campaign_state", "node_sends")
    op.drop_column("drip_node", "repeat_interval_sec")
    op.drop_column("drip_node", "repeat_count")
