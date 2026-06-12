"""add recurring_broadcast_schedule + broadcast.promo_code_id

Revision ID: e2b6d9a4c108
Revises: d8a4f2c1e706
Create Date: 2026-06-13

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e2b6d9a4c108"
down_revision = "d8a4f2c1e706"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_broadcast_schedule",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("audience", sa.String(20), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=True),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("media_kind", sa.String(20), nullable=True),
        sa.Column("media_url", sa.String(512), nullable=True),
        sa.Column("inline_buttons", postgresql.JSONB(), nullable=True),
        sa.Column("promo_code_id", sa.UUID(), nullable=True),
        sa.Column("cadence", sa.String(8), server_default=sa.text("'daily'"), nullable=False),
        sa.Column("time_of_day", sa.String(5), nullable=False),
        sa.Column("weekdays", postgresql.JSONB(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_admin_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plan.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_code.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recurring_broadcast_next_run_at",
        "recurring_broadcast_schedule",
        ["next_run_at"],
    )

    op.add_column("broadcast", sa.Column("promo_code_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_broadcast_promo_code", "broadcast", "promo_code",
        ["promo_code_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_broadcast_promo_code", "broadcast", type_="foreignkey")
    op.drop_column("broadcast", "promo_code_id")
    op.drop_index(
        "ix_recurring_broadcast_next_run_at",
        table_name="recurring_broadcast_schedule",
    )
    op.drop_table("recurring_broadcast_schedule")
