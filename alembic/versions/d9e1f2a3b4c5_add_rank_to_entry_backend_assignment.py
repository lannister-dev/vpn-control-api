"""add rank column to entry_backend_assignment

Rank selects the HAProxy backup tier when the entry node operates in
whitelist_entry mode (`balance first` + `backup` keyword). 0 means primary,
1+ means fallback tiers in ascending order. For entry mode (balance random)
every row stays at 0.

Revision ID: d9e1f2a3b4c5
Revises: c8f2a3b4d5e6
Create Date: 2026-04-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d9e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c8f2a3b4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entry_backend_assignment",
        sa.Column(
            "rank",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_entry_backend_assignment_rank",
        "entry_backend_assignment",
        ["rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entry_backend_assignment_rank",
        table_name="entry_backend_assignment",
    )
    op.drop_column("entry_backend_assignment", "rank")
