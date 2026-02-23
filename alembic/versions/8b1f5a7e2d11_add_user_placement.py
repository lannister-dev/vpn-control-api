"""add user placement

Revision ID: 8b1f5a7e2d11
Revises: 6c2a1b7f4c2d
Create Date: 2026-02-16

"""

from alembic import op
import sqlalchemy as sa


revision = "8b1f5a7e2d11"
down_revision = "6c2a1b7f4c2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_placement",
        sa.Column("key_id", sa.UUID(), nullable=False),
        sa.Column("gateway_node_id", sa.UUID(), nullable=True),
        sa.Column("backend_node_id", sa.UUID(), nullable=False),
        sa.Column("desired_state", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("applied_state", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("op_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("applied_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sticky_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_migration_reason", sa.String(length=64), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["backend_node_id"], ["vpn_node.id"]),
        sa.ForeignKeyConstraint(["gateway_node_id"], ["vpn_node.id"]),
        sa.ForeignKeyConstraint(["key_id"], ["vpn_key.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id", name="uq_user_placement_key_id"),
    )
    op.create_index("ix_user_placement_key_id", "user_placement", ["key_id"], unique=False)
    op.create_index("ix_user_placement_backend_node_id", "user_placement", ["backend_node_id"], unique=False)
    op.create_index("ix_user_placement_gateway_node_id", "user_placement", ["gateway_node_id"], unique=False)
    op.create_index("ix_user_placement_desired_state", "user_placement", ["desired_state"], unique=False)
    op.create_index("ix_user_placement_applied_state", "user_placement", ["applied_state"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_placement_applied_state", table_name="user_placement")
    op.drop_index("ix_user_placement_desired_state", table_name="user_placement")
    op.drop_index("ix_user_placement_gateway_node_id", table_name="user_placement")
    op.drop_index("ix_user_placement_backend_node_id", table_name="user_placement")
    op.drop_index("ix_user_placement_key_id", table_name="user_placement")
    op.drop_table("user_placement")

