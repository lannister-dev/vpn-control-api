"""add alert_events table for admin notifications bell

Revision ID: d4f7a8e9c1b2
Revises: c9e1f3a7b5d2
Create Date: 2026-04-28
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "d4f7a8e9c1b2"
down_revision: Union[str, None] = "c9e1f3a7b5d2"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "alert_events" in inspector.get_table_names():
        return

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=True),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_alert_events_created_at", "alert_events", ["created_at"])
    op.create_index("ix_alert_events_level", "alert_events", ["level"])
    op.create_index("ix_alert_events_source", "alert_events", ["source"])
    op.create_index(
        "ix_alert_events_active_dedup",
        "alert_events",
        ["source", "dedup_key"],
        postgresql_where=sa.text("dedup_key IS NOT NULL AND resolved_at IS NULL AND dismissed_at IS NULL"),
    )
    op.create_index(
        "ix_alert_events_unread",
        "alert_events",
        ["created_at"],
        postgresql_where=sa.text("read_at IS NULL AND dismissed_at IS NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "alert_events" not in inspector.get_table_names():
        return
    op.drop_index("ix_alert_events_unread", table_name="alert_events")
    op.drop_index("ix_alert_events_active_dedup", table_name="alert_events")
    op.drop_index("ix_alert_events_source", table_name="alert_events")
    op.drop_index("ix_alert_events_level", table_name="alert_events")
    op.drop_index("ix_alert_events_created_at", table_name="alert_events")
    op.drop_table("alert_events")
