"""add traffic usage history

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e6f
Create Date: 2026-03-07
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2b3c4d5e6f70"
down_revision: Union[str, None] = "1a2b3c4d5e6f"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.create_table(
        "traffic_usage",
        sa.Column("key_id", sa.UUID(), nullable=False),
        sa.Column("delta_bytes", sa.BigInteger(), nullable=False),
        sa.Column("reported_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["vpn_key.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_traffic_usage_key_id",
        "traffic_usage",
        ["key_id"],
        unique=False,
    )
    op.create_index(
        "ix_traffic_usage_created_at",
        "traffic_usage",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_traffic_usage_created_at",
        table_name="traffic_usage",
    )
    op.drop_index(
        "ix_traffic_usage_key_id",
        table_name="traffic_usage",
    )
    op.drop_table("traffic_usage")
