"""add user tag/description and plan table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-20
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # --- User: add tag, description ---
    user_columns = {c["name"] for c in inspector.get_columns("user")}
    if "tag" not in user_columns:
        op.add_column("user", sa.Column("tag", sa.String(32), nullable=True))
    if "description" not in user_columns:
        op.add_column("user", sa.Column("description", sa.Text(), nullable=True))

    # --- Plan table ---
    if not inspector.has_table("plan"):
        op.create_table(
            "plan",
            sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("reset_strategy", sa.String(16), nullable=False, server_default=sa.text("'NO_RESET'")),
            sa.Column("max_devices", sa.Integer(), nullable=False, server_default=sa.text("5")),
            sa.Column("duration_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )


def downgrade() -> None:
    op.drop_table("plan")
    op.drop_column("user", "description")
    op.drop_column("user", "tag")
