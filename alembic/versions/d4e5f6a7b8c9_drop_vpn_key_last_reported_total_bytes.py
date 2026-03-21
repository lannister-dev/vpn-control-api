"""simplify traffic: drop key_node_traffic_counter table and last_reported_total_bytes

Revision ID: d4e5f6a7b8c9
Revises: a1c2d3e4f5b6
Create Date: 2026-03-21
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "a1c2d3e4f5b6"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_key_node_traffic_counter_key_id", table_name="key_node_traffic_counter")
    op.drop_table("key_node_traffic_counter")
    op.drop_column("vpn_key", "last_reported_total_bytes")


def downgrade() -> None:
    op.add_column(
        "vpn_key",
        sa.Column(
            "last_reported_total_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_table(
        "key_node_traffic_counter",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("vpn_key.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("last_reported_total_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id", "node_id", name="uq_key_node_traffic_counter"),
    )
    op.create_index("ix_key_node_traffic_counter_key_id", "key_node_traffic_counter", ["key_id"])
