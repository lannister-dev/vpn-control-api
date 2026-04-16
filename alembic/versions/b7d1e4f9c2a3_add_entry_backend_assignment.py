"""add entry_backend_assignment table

Revision ID: b7d1e4f9c2a3
Revises: a3b4c5d6e7f8
Create Date: 2026-04-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7d1e4f9c2a3"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entry_backend_assignment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("entry_node_id", sa.UUID(), nullable=False),
        sa.Column("backend_node_id", sa.UUID(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["entry_node_id"], ["vpn_node.id"]),
        sa.ForeignKeyConstraint(["backend_node_id"], ["vpn_node.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entry_node_id",
            "backend_node_id",
            name="uq_entry_backend_assignment_entry_backend",
        ),
    )
    op.create_index(
        "ix_entry_backend_assignment_entry_node_id",
        "entry_backend_assignment",
        ["entry_node_id"],
        unique=False,
    )
    op.create_index(
        "ix_entry_backend_assignment_backend_node_id",
        "entry_backend_assignment",
        ["backend_node_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entry_backend_assignment_backend_node_id",
        table_name="entry_backend_assignment",
    )
    op.drop_index(
        "ix_entry_backend_assignment_entry_node_id",
        table_name="entry_backend_assignment",
    )
    op.drop_table("entry_backend_assignment")
