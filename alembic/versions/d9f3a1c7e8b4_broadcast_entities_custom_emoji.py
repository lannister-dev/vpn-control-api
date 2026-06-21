"""broadcast entities + custom emoji assets

Revision ID: d9f3a1c7e8b4
Revises: b1c2d3e4f5a6
Create Date: 2026-06-21
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9f3a1c7e8b4"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broadcast",
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "broadcast",
        sa.Column("custom_emoji_assets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("broadcast", "custom_emoji_assets")
    op.drop_column("broadcast", "entities")
