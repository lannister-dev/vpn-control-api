"""add plan_period table and period_months

Revision ID: c7a1f5b9d234
Revises: b9e4f7c2d810
Create Date: 2026-06-01

"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "c7a1f5b9d234"
down_revision = "b9e4f7c2d810"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_period",
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("price_rub", sa.Numeric(10, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("price_stars", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "months", name="uq_plan_period_plan_months"),
    )
    op.create_index("ix_plan_period_plan_id", "plan_period", ["plan_id"], unique=False)

    op.add_column(
        "subscription",
        sa.Column("period_months", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "payment_order",
        sa.Column("period_months", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )

    _backfill_periods()


def _backfill_periods() -> None:
    bind = op.get_bind()
    plans = bind.execute(
        sa.text("SELECT id, price_rub, price_stars FROM plan")
    ).fetchall()
    for plan in plans:
        bind.execute(
            sa.text(
                "INSERT INTO plan_period "
                "(id, plan_id, months, price_rub, price_stars, created_at, updated_at, is_active) "
                "VALUES (:id, :plan_id, 1, :price_rub, :price_stars, now(), now(), true)"
            ),
            {
                "id": uuid.uuid4(),
                "plan_id": plan.id,
                "price_rub": plan.price_rub,
                "price_stars": plan.price_stars,
            },
        )


def downgrade() -> None:
    op.drop_column("payment_order", "period_months")
    op.drop_column("subscription", "period_months")
    op.drop_index("ix_plan_period_plan_id", table_name="plan_period")
    op.drop_table("plan_period")
