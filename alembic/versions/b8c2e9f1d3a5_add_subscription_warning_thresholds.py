"""add traffic_warning_threshold_pct to subscription

Revision ID: b8c2e9f1d3a5
Revises: a1b5c9d3e7f2
Create Date: 2026-04-26
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "b8c2e9f1d3a5"
down_revision: Union[str, None] = "a1b5c9d3e7f2"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("subscription")}

    if "traffic_warning_threshold_pct" not in cols:
        op.add_column(
            "subscription",
            sa.Column(
                "traffic_warning_threshold_pct",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("subscription")}

    if "traffic_warning_threshold_pct" in cols:
        op.drop_column("subscription", "traffic_warning_threshold_pct")
