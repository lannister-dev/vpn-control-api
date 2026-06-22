"""lifecycle signals: user.suppress_marketing + subscription.first_connected_at

Revision ID: e7a2b9c4d1f8
Revises: d9f3a1c7e8b4
Create Date: 2026-06-22
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "e7a2b9c4d1f8"
down_revision: Union[str, None] = "d9f3a1c7e8b4"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "suppress_marketing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "subscription",
        sa.Column("first_connected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscription", "first_connected_at")
    op.drop_column("user", "suppress_marketing")
