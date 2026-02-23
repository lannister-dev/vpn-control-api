"""drop backend_peer table

Revision ID: d6a31b0c9e7f
Revises: 1f2c9e8d4b11
Create Date: 2026-02-19
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6a31b0c9e7f"
down_revision: Union[str, None] = "1f2c9e8d4b11"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.drop_table("backend_peer")


def downgrade() -> None:
    op.create_table(
        "backend_peer",
        sa.Column("backend_node_id", sa.UUID(), nullable=False),
        sa.Column("gateway_node_id", sa.UUID(), nullable=False),
        sa.Column("internal_uuid", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("applied_state", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("op_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("applied_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("op_version >= 1", name="ck_backend_peer_op_version_ge_1"),
        sa.CheckConstraint("applied_version >= 0", name="ck_backend_peer_applied_version_ge_0"),
        sa.CheckConstraint("applied_version <= op_version", name="ck_backend_peer_applied_version_lte_op"),
        sa.ForeignKeyConstraint(["backend_node_id"], ["vpn_node.id"]),
        sa.ForeignKeyConstraint(["gateway_node_id"], ["vpn_node.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_uuid"),
        sa.UniqueConstraint("backend_node_id", "gateway_node_id", name="uq_backend_peer_pair"),
    )
    op.create_index("ix_backend_peer_backend_node_id", "backend_peer", ["backend_node_id"], unique=False)
    op.create_index("ix_backend_peer_gateway_node_id", "backend_peer", ["gateway_node_id"], unique=False)
    op.create_index("ix_backend_peer_status", "backend_peer", ["status"], unique=False)
    op.create_index("ix_backend_peer_applied_state", "backend_peer", ["applied_state"], unique=False)
