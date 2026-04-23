"""node policy singleton table

Moves operational NodeAgent tunables (auto-heal, placement reconcilers,
entry pool drain) from env to DB. Bootstrap-only fields
(sync_report_debounce_sec, auth_token_rotation_grace_sec, bootstrap_allow_create)
remain in env — they're protocol/security wiring, not knobs.

Revision ID: a1b5c9d3e7f2
Revises: f0a2b4c6d8e1
Create Date: 2026-04-23
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b5c9d3e7f2"
down_revision: Union[str, None] = "f0a2b4c6d8e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "node_policy",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("stale_after_sec", sa.Integer(), nullable=False, server_default=sa.text("90")),
        sa.Column("heartbeat_unhealthy_drain_threshold", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("heartbeat_healthy_undrain_threshold", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("auto_heal_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_heal_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("auto_heal_max_nodes", sa.Integer(), nullable=False, server_default=sa.text("20")),
        sa.Column("auto_heal_drain_cooldown_sec", sa.Integer(), nullable=False, server_default=sa.text("180")),
        sa.Column("auto_undrain_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("placement_error_retry_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("placement_error_retry_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("placement_error_retry_after_sec", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("placement_rebalance_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("placement_rebalance_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("placement_rebalance_batch_size", sa.Integer(), nullable=False, server_default=sa.text("200")),
        sa.Column("entry_apply_fail_threshold", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("entry_apply_fail_unhealthy", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("entry_auto_drain_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("entry_auto_drain_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("entry_auto_drain_probe_failures", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("entry_auto_drain_max_nodes", sa.Integer(), nullable=False, server_default=sa.text("50")),
        sa.Column("entry_auto_drain_reason", sa.String(length=64), nullable=False, server_default=sa.text("'entry_auto_drain'")),
        sa.Column("entry_auto_undrain_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("entry_auto_undrain_healthy_ticks", sa.Integer(), nullable=False, server_default=sa.text("3")),
    )
    op.execute("INSERT INTO node_policy (id) VALUES (gen_random_uuid())")


def downgrade() -> None:
    op.drop_table("node_policy")
