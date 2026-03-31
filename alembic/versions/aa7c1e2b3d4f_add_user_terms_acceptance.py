"""add user terms acceptance fields

Revision ID: aa7c1e2b3d4f
Revises: c3d4e5f6a7b8
Create Date: 2026-03-29 12:00:00.000000
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "aa7c1e2b3d4f"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {c["name"] for c in inspector.get_columns("user")}
    added_terms_accepted = False
    added_terms_accepted_at = False

    if "terms_accepted" not in user_columns:
        op.add_column(
            "user",
            sa.Column(
                "terms_accepted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        added_terms_accepted = True

    if "terms_accepted_at" not in user_columns:
        op.add_column(
            "user",
            sa.Column(
                "terms_accepted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        added_terms_accepted_at = True

    if added_terms_accepted:
        op.execute(
            sa.text(
                """
                UPDATE "user"
                SET terms_accepted = true
                WHERE terms_accepted = false
                """
            )
        )

    if added_terms_accepted or added_terms_accepted_at:
        op.execute(
            sa.text(
                """
                UPDATE "user"
                SET terms_accepted_at = COALESCE(terms_accepted_at, created_at)
                WHERE terms_accepted = true
                  AND terms_accepted_at IS NULL
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {c["name"] for c in inspector.get_columns("user")}

    if "terms_accepted_at" in user_columns:
        op.drop_column("user", "terms_accepted_at")

    if "terms_accepted" in user_columns:
        op.drop_column("user", "terms_accepted")
