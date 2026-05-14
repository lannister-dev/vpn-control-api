"""support module tables

Revision ID: e5f7a2b1c8d4
Revises: d2a8c5e7f3b1
Create Date: 2026-05-13
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5f7a2b1c8d4"
down_revision: Union[str, None] = "d2a8c5e7f3b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base_cols():
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "support_ticket",
        *_base_cols(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("category", sa.String(20), nullable=False, server_default="other"),
        sa.Column("assignee_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_user_msg_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_reply_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_support_ticket_user_id", "support_ticket", ["user_id"])
    op.create_index("ix_support_ticket_assignee_admin_id", "support_ticket", ["assignee_admin_id"])
    op.create_index("ix_support_ticket_last_activity_at", "support_ticket", ["last_activity_at"])
    op.create_index("ix_support_ticket_status_activity", "support_ticket", ["status", "last_activity_at"])

    op.create_table(
        "support_message",
        *_base_cols(),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("support_ticket.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_kind", sa.String(10), nullable=False),
        sa.Column("sender_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_note", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_support_message_ticket_id", "support_message", ["ticket_id"])

    op.create_table(
        "support_attachment",
        *_base_cols(),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("support_message.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("tg_file_id", sa.String(256), nullable=True),
        sa.Column("tg_file_unique_id", sa.String(64), nullable=True),
        sa.Column("file_name", sa.String(256), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(80), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("storage_url", sa.String(512), nullable=True),
    )
    op.create_index("ix_support_attachment_message_id", "support_attachment", ["message_id"])

    op.create_table(
        "support_template",
        *_base_cols(),
        sa.Column("tag", sa.String(40), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_support_template_tag", "support_template", ["tag"])

    op.create_table(
        "broadcast",
        *_base_cols(),
        sa.Column("audience", sa.String(20), nullable=False),
        sa.Column("audience_label", sa.String(120), nullable=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plan.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("media_kind", sa.String(20), nullable=True),
        sa.Column("media_url", sa.String(512), nullable=True),
        sa.Column("inline_buttons", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_user.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "broadcast_log",
        *_base_cols(),
        sa.Column("broadcast_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("broadcast.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(200), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_broadcast_log_broadcast_id", "broadcast_log", ["broadcast_id"])


def downgrade() -> None:
    op.drop_index("ix_broadcast_log_broadcast_id", table_name="broadcast_log")
    op.drop_table("broadcast_log")
    op.drop_table("broadcast")
    op.drop_index("ix_support_template_tag", table_name="support_template")
    op.drop_table("support_template")
    op.drop_index("ix_support_attachment_message_id", table_name="support_attachment")
    op.drop_table("support_attachment")
    op.drop_index("ix_support_message_ticket_id", table_name="support_message")
    op.drop_table("support_message")
    op.drop_index("ix_support_ticket_status_activity", table_name="support_ticket")
    op.drop_index("ix_support_ticket_last_activity_at", table_name="support_ticket")
    op.drop_index("ix_support_ticket_assignee_admin_id", table_name="support_ticket")
    op.drop_index("ix_support_ticket_user_id", table_name="support_ticket")
    op.drop_table("support_ticket")
