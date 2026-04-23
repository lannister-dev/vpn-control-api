"""admin audit log

Stores actor-scoped audit trail for admin-facing mutations (migrate-backend,
set-route-health, probe policy changes, etc.). Surfaced in control panel Ops
page as "Recent operations" feed and per-user filter.

Revision ID: e5d2c4b8a1f3
Revises: a4e1d8b2f5c6
Create Date: 2026-04-23
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e5d2c4b8a1f3"
down_revision: Union[str, None] = "a4e1d8b2f5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.String(length=512), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_admin_audit_created_at", "admin_audit_log", ["created_at"])
    op.create_index("ix_admin_audit_action", "admin_audit_log", ["action"])
    op.create_index("ix_admin_audit_actor", "admin_audit_log", ["actor"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_actor", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_action", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
