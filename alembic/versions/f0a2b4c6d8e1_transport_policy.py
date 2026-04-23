"""transport policy singleton table

Moves TRANSPORT_CLEANUP_ENABLED / TRANSPORT_CLEANUP_TICK_SEC /
TRANSPORT_RETENTION_DAYS from env to DB-backed admin-tunable policy.

Revision ID: f0a2b4c6d8e1
Revises: e5d2c4b8a1f3
Create Date: 2026-04-23
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "f0a2b4c6d8e1"
down_revision: Union[str, None] = "e5d2c4b8a1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transport_policy",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("cleanup_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("cleanup_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("3600")),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
    )
    op.execute("INSERT INTO transport_policy (id) VALUES (gen_random_uuid())")


def downgrade() -> None:
    op.drop_table("transport_policy")
