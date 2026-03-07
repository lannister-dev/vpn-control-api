"""add user placement backend/op cursor index

Revision ID: f13be8a1d2c4
Revises: d6a31b0c9e7f
Create Date: 2026-02-22
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f13be8a1d2c4"
down_revision: Union[str, None] = "d6a31b0c9e7f"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_user_placement_backend_node_op_version_id_active",
        "user_placement",
        ["backend_node_id", "op_version", "id"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_placement_backend_node_op_version_id_active",
        table_name="user_placement",
    )
