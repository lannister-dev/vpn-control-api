"""extend probe_policy with remaining tunables from ENV

Moves operational knobs out of env into DB: retention, cleanup, synthetic
reconcile, drain source/target/reason flags. Bootstrap-only items
(PROBE_TARGET_PORT, synthetic client_ids, synthetic user identity) stay in env.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-04-23
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("probe_policy", sa.Column("auto_route_health_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))

    op.add_column("probe_policy", sa.Column("auto_drain_source", sa.String(length=64), nullable=True))
    op.add_column("probe_policy", sa.Column("auto_drain_require_recent_failure", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("probe_policy", sa.Column("auto_drain_include_already_draining", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("probe_policy", sa.Column("auto_drain_target_backend_id", sa.UUID(), sa.ForeignKey("vpn_node.id", ondelete="SET NULL"), nullable=True))
    op.add_column("probe_policy", sa.Column("auto_drain_last_migration_reason", sa.String(length=64), nullable=False, server_default=sa.text("'probe_auto_failure'")))

    op.add_column("probe_policy", sa.Column("auto_undrain_source", sa.String(length=64), nullable=True))

    op.add_column("probe_policy", sa.Column("retention_days", sa.Integer(), nullable=False, server_default=sa.text("3")))
    op.add_column("probe_policy", sa.Column("cleanup_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("probe_policy", sa.Column("cleanup_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("3600")))

    op.add_column("probe_policy", sa.Column("synthetic_reconcile_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("probe_policy", sa.Column("synthetic_reconcile_tick_sec", sa.Integer(), nullable=False, server_default=sa.text("300")))
    op.add_column("probe_policy", sa.Column("synthetic_key_valid_days", sa.Integer(), nullable=False, server_default=sa.text("3650")))
    op.add_column("probe_policy", sa.Column("synthetic_key_traffic_limit_mb", sa.Integer(), nullable=False, server_default=sa.text("102400")))


def downgrade() -> None:
    for col in [
        "synthetic_key_traffic_limit_mb",
        "synthetic_key_valid_days",
        "synthetic_reconcile_tick_sec",
        "synthetic_reconcile_enabled",
        "cleanup_tick_sec",
        "cleanup_enabled",
        "retention_days",
        "auto_undrain_source",
        "auto_drain_last_migration_reason",
        "auto_drain_target_backend_id",
        "auto_drain_include_already_draining",
        "auto_drain_require_recent_failure",
        "auto_drain_source",
        "auto_route_health_enabled",
    ]:
        op.drop_column("probe_policy", col)
