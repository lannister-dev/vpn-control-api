"""probe_policy: add is_active column inherited from Base

Revision ID: a4e1d8b2f5c6
Revises: b3c7a1f9d52e
Create Date: 2026-04-23
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "a4e1d8b2f5c6"
down_revision: Union[str, None] = "b3c7a1f9d52e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "probe_policy",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("probe_policy", "is_active")
