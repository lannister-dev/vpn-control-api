"""add node_agent_identity table for per-agent node auth

Revision ID: f9a2d7c4b5e1
Revises: f13be8a1d2c4
Create Date: 2026-02-26
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9a2d7c4b5e1"
down_revision: Union[str, None] = "f13be8a1d2c4"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.create_table(
        "node_agent_identity",
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("agent_instance_id", sa.UUID(), nullable=False),
        sa.Column("auth_token_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["vpn_node.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "node_id",
            "agent_instance_id",
            name="uq_node_agent_identity_node_agent",
        ),
    )
    op.create_index(
        "ix_node_agent_identity_node_id",
        "node_agent_identity",
        ["node_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_node_agent_identity_node_id", table_name="node_agent_identity")
    op.drop_table("node_agent_identity")
