"""add admin auth tables

Revision ID: 3c4d5e6f7a81
Revises: 2b3c4d5e6f70
Create Date: 2026-03-08
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "3c4d5e6f7a81"
down_revision: Union[str, None] = "2b3c4d5e6f70"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("admin_user"):
        op.create_table(
            "admin_user",
            sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
            sa.Column("username", sa.String(64), nullable=False),
            sa.Column("password_hash", sa.String(256), nullable=True),
            sa.Column("telegram_id", sa.BigInteger(), nullable=True),
            sa.Column("telegram_username", sa.String(128), nullable=True),
            sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
            sa.UniqueConstraint("telegram_id"),
        )

    if not inspector.has_table("admin_session"):
        op.create_table(
            "admin_session",
            sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("session_hash", sa.String(128), nullable=False),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(512), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_hash"),
            sa.ForeignKeyConstraint(["user_id"], ["admin_user.id"], ondelete="CASCADE"),
        )
    session_indexes = {item["name"] for item in inspector.get_indexes("admin_session")} if inspector.has_table("admin_session") else set()
    if "ix_admin_session_expires_at" not in session_indexes:
        op.create_index("ix_admin_session_expires_at", "admin_session", ["expires_at"])

    if not inspector.has_table("admin_audit_event"):
        op.create_table(
            "admin_audit_event",
            sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["user_id"], ["admin_user.id"], ondelete="SET NULL"),
        )
    audit_indexes = {item["name"] for item in inspector.get_indexes("admin_audit_event")} if inspector.has_table("admin_audit_event") else set()
    if "ix_admin_audit_event_action" not in audit_indexes:
        op.create_index("ix_admin_audit_event_action", "admin_audit_event", ["action"])
    if "ix_admin_audit_event_created_at" not in audit_indexes:
        op.create_index("ix_admin_audit_event_created_at", "admin_audit_event", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_event_created_at", table_name="admin_audit_event")
    op.drop_index("ix_admin_audit_event_action", table_name="admin_audit_event")
    op.drop_table("admin_audit_event")
    op.drop_index("ix_admin_session_expires_at", table_name="admin_session")
    op.drop_table("admin_session")
    op.drop_table("admin_user")
