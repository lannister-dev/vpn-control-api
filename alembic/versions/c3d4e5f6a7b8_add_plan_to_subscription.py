"""add plan_id to subscription, traffic fields, subscription_id to vpn_key

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-20
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # --- Subscription: add plan_id, traffic tracking fields ---
    sub_columns = {c["name"] for c in inspector.get_columns("subscription")}

    if "plan_id" not in sub_columns:
        op.add_column(
            "subscription",
            sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("plan.id"), nullable=True),
        )
        op.create_index("ix_subscription_plan_id", "subscription", ["plan_id"])

    if "used_traffic_bytes" not in sub_columns:
        op.add_column(
            "subscription",
            sa.Column(
                "used_traffic_bytes",
                sa.BigInteger(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    if "lifetime_used_traffic_bytes" not in sub_columns:
        op.add_column(
            "subscription",
            sa.Column(
                "lifetime_used_traffic_bytes",
                sa.BigInteger(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    if "last_traffic_reset_at" not in sub_columns:
        op.add_column(
            "subscription",
            sa.Column(
                "last_traffic_reset_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    # --- VpnKey: add subscription_id ---
    key_columns = {c["name"] for c in inspector.get_columns("vpn_key")}

    if "subscription_id" not in key_columns:
        op.add_column(
            "vpn_key",
            sa.Column(
                "subscription_id",
                sa.Uuid(),
                sa.ForeignKey("subscription.id"),
                nullable=True,
            ),
        )
        op.create_index("ix_vpn_key_subscription_id", "vpn_key", ["subscription_id"])


def downgrade() -> None:
    op.drop_index("ix_vpn_key_subscription_id", table_name="vpn_key")
    op.drop_column("vpn_key", "subscription_id")
    op.drop_index("ix_subscription_plan_id", table_name="subscription")
    op.drop_column("subscription", "last_traffic_reset_at")
    op.drop_column("subscription", "lifetime_used_traffic_bytes")
    op.drop_column("subscription", "used_traffic_bytes")
    op.drop_column("subscription", "plan_id")
