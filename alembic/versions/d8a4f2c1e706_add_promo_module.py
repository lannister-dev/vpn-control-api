"""add promo_code, promo_activation + order promo columns

Revision ID: d8a4f2c1e706
Revises: c3f7a1b9e204
Create Date: 2026-06-12

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d8a4f2c1e706"
down_revision = "c3f7a1b9e204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promo_code",
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("description", sa.String(256), nullable=True),
        sa.Column("discount_type", sa.String(8), nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_discount_rub", sa.Numeric(10, 2), nullable=True),
        sa.Column("audience", sa.String(20), server_default=sa.text("'all'"), nullable=False),
        sa.Column("plan_ids", postgresql.JSONB(), nullable=True),
        sa.Column("applies_to", sa.String(16), server_default=sa.text("'any'"), nullable=False),
        sa.Column("min_amount_rub", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_activations", sa.Integer(), nullable=True),
        sa.Column("max_per_user", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activation_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_admin_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_promo_code_code"),
    )
    op.create_index("ix_promo_code_code", "promo_code", ["code"])
    op.create_index("ix_promo_code_is_active", "promo_code", ["is_active"])

    op.create_table(
        "promo_activation",
        sa.Column("promo_code_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("amount_before", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount_applied", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount_after", sa.Numeric(10, 2), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_code.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["payment_order.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_promo_activation_promo_code_id", "promo_activation", ["promo_code_id"])
    op.create_index("ix_promo_activation_user_id", "promo_activation", ["user_id"])
    op.create_index("ix_promo_activation_promo_user", "promo_activation", ["promo_code_id", "user_id"])

    op.add_column("payment_order", sa.Column("promo_code_id", sa.UUID(), nullable=True))
    op.add_column("payment_order", sa.Column("discount_rub", sa.Numeric(10, 2), nullable=True))
    op.create_foreign_key(
        "fk_payment_order_promo_code", "payment_order", "promo_code",
        ["promo_code_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_payment_order_promo_code", "payment_order", type_="foreignkey")
    op.drop_column("payment_order", "discount_rub")
    op.drop_column("payment_order", "promo_code_id")
    op.drop_index("ix_promo_activation_promo_user", table_name="promo_activation")
    op.drop_index("ix_promo_activation_user_id", table_name="promo_activation")
    op.drop_index("ix_promo_activation_promo_code_id", table_name="promo_activation")
    op.drop_table("promo_activation")
    op.drop_index("ix_promo_code_is_active", table_name="promo_code")
    op.drop_index("ix_promo_code_code", table_name="promo_code")
    op.drop_table("promo_code")
