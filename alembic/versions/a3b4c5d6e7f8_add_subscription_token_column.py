"""add subscription token column

Revision ID: a3b4c5d6e7f8
Revises: d8e9f0a1b2c3
Create Date: 2026-04-13 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("subscription", sa.Column("token", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("subscription", "token")
