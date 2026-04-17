"""add plan.entry_relay_enabled column

Revision ID: c8f2a3b4d5e6
Revises: b7d1e4f9c2a3
Create Date: 2026-04-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8f2a3b4d5e6"
down_revision: Union[str, Sequence[str], None] = "c5a9b2e7f3d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan",
        sa.Column(
            "entry_relay_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("plan", "entry_relay_enabled")
