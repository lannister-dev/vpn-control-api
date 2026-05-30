"""drop key_assignment table

Revision ID: b9e4f7c2d810
Revises: a7b9d3e5f8c1
Create Date: 2026-05-30
"""

from typing import Union

from alembic import op


revision: str = "b9e4f7c2d810"
down_revision: Union[str, None] = "a7b9d3e5f8c1"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS key_assignment CASCADE")


def downgrade() -> None:
    raise NotImplementedError("key_assignment table is permanently removed")
