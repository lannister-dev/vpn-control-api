"""admin_user.ui_prefs (sidebar customization)

Revision ID: c5e2f8a4b9d1
Revises: b4c1e9f72a30
Create Date: 2026-06-22
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c5e2f8a4b9d1"
down_revision: Union[str, None] = "b4c1e9f72a30"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_user",
        sa.Column("ui_prefs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_user", "ui_prefs")
