"""traffic policy singleton table

Moves user/node traffic cleanup knobs from env to DB-backed admin-tunable policy.

Revision ID: c5d8e2f4a9b3
Revises: d4f7a8e9c1b2
Create Date: 2026-04-30
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "c5d8e2f4a9b3"
down_revision: Union[str, None] = "d4f7a8e9c1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traffic_policy",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("user_cleanup_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("user_cleanup_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("3600")),
        sa.Column("user_retention_days", sa.Integer(), nullable=False, server_default=sa.text("35")),
        sa.Column("node_cleanup_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("node_cleanup_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("3600")),
        sa.Column("node_retention_days", sa.Integer(), nullable=False, server_default=sa.text("90")),
    )
    op.execute("INSERT INTO traffic_policy (id) VALUES (gen_random_uuid())")


def downgrade() -> None:
    op.drop_table("traffic_policy")
