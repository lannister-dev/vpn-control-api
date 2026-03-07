"""user_placement multi-home unique key

Revision ID: ab12c3d4e5f6
Revises: fa31b8e2c4d7
Create Date: 2026-02-28
"""

from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ab12c3d4e5f6"
down_revision: Union[str, None] = "fa31b8e2c4d7"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_user_placement_key_id", "user_placement", type_="unique")
    op.create_unique_constraint(
        "uq_user_placement_key_backend",
        "user_placement",
        ["key_id", "backend_node_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_placement_key_backend", "user_placement", type_="unique")
    op.create_unique_constraint(
        "uq_user_placement_key_id",
        "user_placement",
        ["key_id"],
    )
