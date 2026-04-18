"""make node_traffic_usage.entry_node_id nullable

Backend-role agents publish node-level traffic under
(entry_node_id=NULL, backend_node_id=self) — entries are only known by
entry-side agents, so requiring NOT NULL forced the schema to lie.

Revision ID: f2a3b4c5d6e7
Revises: e1b2c3d4f5a6
Create Date: 2026-04-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1b2c3d4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "node_traffic_usage",
        "entry_node_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM node_traffic_usage WHERE entry_node_id IS NULL")
    op.alter_column(
        "node_traffic_usage",
        "entry_node_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
