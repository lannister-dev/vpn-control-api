"""subscription.auto_renew (balance autorenew opt-in)

Revision ID: b4c1e9f72a30
Revises: f3b8d6a1c0e9
Create Date: 2026-06-22
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "b4c1e9f72a30"
down_revision: Union[str, None] = "f3b8d6a1c0e9"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription",
        sa.Column(
            "auto_renew",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("subscription", "auto_renew")
