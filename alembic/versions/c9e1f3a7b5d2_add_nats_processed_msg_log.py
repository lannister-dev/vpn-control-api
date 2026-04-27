"""add nats_processed_msg_log table for consumer-side dedup

Revision ID: c9e1f3a7b5d2
Revises: b8c2e9f1d3a5
Create Date: 2026-04-26
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "c9e1f3a7b5d2"
down_revision: Union[str, None] = "b8c2e9f1d3a5"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "nats_processed_msg_log" in inspector.get_table_names():
        return

    op.create_table(
        "nats_processed_msg_log",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("msg_id", sa.String(length=128), nullable=False),
        sa.Column("subject", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("subject", "msg_id", name="uq_nats_processed_msg_subject_msg_id"),
    )
    op.create_index(
        "ix_nats_processed_msg_log_created_at",
        "nats_processed_msg_log",
        ["created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "nats_processed_msg_log" not in inspector.get_table_names():
        return
    op.drop_index("ix_nats_processed_msg_log_created_at", table_name="nats_processed_msg_log")
    op.drop_table("nats_processed_msg_log")
