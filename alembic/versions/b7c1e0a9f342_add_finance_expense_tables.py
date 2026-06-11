"""add expense and recurring_expense_template tables

Revision ID: b7c1e0a9f342
Revises: d4e8f1a6c302
Create Date: 2026-06-10

"""

import sqlalchemy as sa

from alembic import op

revision = "b7c1e0a9f342"
down_revision = "d4e8f1a6c302"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_expense_template",
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'RUB'"), nullable=False),
        sa.Column("fx_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vendor", sa.String(64), nullable=True),
        sa.Column("region", sa.String(32), nullable=True),
        sa.Column("description", sa.String(256), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recurring_expense_template_next_run_at",
        "recurring_expense_template",
        ["next_run_at"],
    )

    op.create_table(
        "expense",
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'RUB'"), nullable=False),
        sa.Column("amount_rub", sa.Numeric(12, 2), nullable=False),
        sa.Column("fx_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column("incurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vendor", sa.String(64), nullable=True),
        sa.Column("region", sa.String(32), nullable=True),
        sa.Column("description", sa.String(256), nullable=True),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["template_id"], ["recurring_expense_template.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expense_kind", "expense", ["kind"])
    op.create_index("ix_expense_incurred_at", "expense", ["incurred_at"])
    op.create_index("ix_expense_template_id", "expense", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_expense_template_id", table_name="expense")
    op.drop_index("ix_expense_incurred_at", table_name="expense")
    op.drop_index("ix_expense_kind", table_name="expense")
    op.drop_table("expense")
    op.drop_index(
        "ix_recurring_expense_template_next_run_at",
        table_name="recurring_expense_template",
    )
    op.drop_table("recurring_expense_template")
