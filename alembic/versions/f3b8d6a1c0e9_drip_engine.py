"""drip engine: drip_campaign + drip_step + user_campaign_state

Revision ID: f3b8d6a1c0e9
Revises: e7a2b9c4d1f8
Create Date: 2026-06-22
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3b8d6a1c0e9"
down_revision: Union[str, None] = "e7a2b9c4d1f8"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drip_campaign",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("trigger_event", sa.String(length=48), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "drip_step",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("drip_campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("delay_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("condition", sa.String(length=32), nullable=False, server_default=sa.text("'always'")),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("inline_buttons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("media_kind", sa.String(length=16), nullable=True),
        sa.Column("media_url", sa.String(length=512), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "step_order", name="uq_drip_step_campaign_order"),
    )

    op.create_table(
        "user_campaign_state",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("drip_campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_send_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_step_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "campaign_id", name="uq_user_campaign"),
    )
    op.create_index(
        "ix_user_campaign_due", "user_campaign_state", ["status", "next_send_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_campaign_due", table_name="user_campaign_state")
    op.drop_table("user_campaign_state")
    op.drop_table("drip_step")
    op.drop_table("drip_campaign")
