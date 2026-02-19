"""add backend peer table

Revision ID: c2f94b9e1a11
Revises: 9c41e5d7a6b2
Create Date: 2026-02-16

"""

from alembic import op
import sqlalchemy as sa


revision = "c2f94b9e1a11"
down_revision = "9c41e5d7a6b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("ix_backend_peer_applied_state", table_name="backend_peer")
    op.drop_index("ix_backend_peer_status", table_name="backend_peer")
    op.drop_index("ix_backend_peer_gateway_node_id", table_name="backend_peer")
    op.drop_index("ix_backend_peer_backend_node_id", table_name="backend_peer")
    op.drop_table("backend_peer")
