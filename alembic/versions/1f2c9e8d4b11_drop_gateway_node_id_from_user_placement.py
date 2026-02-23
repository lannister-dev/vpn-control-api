"""drop gateway_node_id from user_placement

Revision ID: 1f2c9e8d4b11
Revises: a4d8e7c91f20
Create Date: 2026-02-19 21:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1f2c9e8d4b11"
down_revision: Union[str, None] = "a4d8e7c91f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_placement DROP COLUMN IF EXISTS gateway_node_id")


def downgrade() -> None:
    op.add_column("user_placement", sa.Column("gateway_node_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        None,
        "user_placement",
        "vpn_node",
        ["gateway_node_id"],
        ["id"],
    )
    op.create_index(
        "ix_user_placement_gateway_node_id",
        "user_placement",
        ["gateway_node_id"],
        unique=False,
    )
