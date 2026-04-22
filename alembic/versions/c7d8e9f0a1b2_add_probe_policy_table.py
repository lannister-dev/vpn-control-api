"""add probe_policy singleton table

Stores tunable thresholds for route health decisions and auto-drain/undrain
behaviour. Values were previously read from env on service startup; now
they live in DB so admins can tune them via the control panel UI at runtime.

Revision ID: c7d8e9f0a1b2
Revises: e1a2b3c4d5f6
Create Date: 2026-04-23
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "e1a2b3c4d5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "probe_policy",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("route_suspected_after_failures", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("route_degraded_after_failures", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("route_block_after_failures", sa.Integer(), nullable=False, server_default=sa.text("4")),
        sa.Column("route_block_cooldown_hours", sa.Integer(), nullable=False, server_default=sa.text("6")),
        sa.Column("auto_drain_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_drain_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("auto_drain_min_consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("auto_drain_max_probe_age_sec", sa.Integer(), nullable=False, server_default=sa.text("600")),
        sa.Column("auto_drain_max_nodes", sa.Integer(), nullable=False, server_default=sa.text("20")),
        sa.Column("auto_undrain_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_undrain_min_consecutive_successes", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("auto_undrain_max_probe_age_sec", sa.Integer(), nullable=False, server_default=sa.text("600")),
    )
    op.execute("INSERT INTO probe_policy (id) VALUES (gen_random_uuid())")


def downgrade() -> None:
    op.drop_table("probe_policy")
