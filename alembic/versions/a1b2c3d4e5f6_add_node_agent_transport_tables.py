"""add node agent transport tables

Revision ID: a1b2c3d4e5f6
Revises: 9f1c2d3e4b5a
Create Date: 2026-03-16 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9f1c2d3e4b5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "node_transport_outbox",
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vpn_node.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("op_version", sa.Integer(), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index("ix_node_transport_outbox_node_id", "node_transport_outbox", ["node_id"])
    op.create_index("ix_node_transport_outbox_aggregate_id", "node_transport_outbox", ["aggregate_id"])
    op.create_index(
        "ix_node_transport_outbox_status_retry",
        "node_transport_outbox",
        ["status", "next_retry_at", "created_at"],
    )

    op.create_table(
        "node_transport_event_log",
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vpn_node.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_node_transport_event_log_node_id", "node_transport_event_log", ["node_id"])
    op.create_index(
        "ix_node_transport_event_log_node_type",
        "node_transport_event_log",
        ["node_id", "event_type", "processed_at"],
    )

    op.create_table(
        "node_transport_state",
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vpn_node.id"), nullable=False),
        sa.Column("current_epoch", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_snapshot_id", sa.String(length=128), nullable=True),
        sa.Column("last_snapshot_request_event_id", sa.String(length=255), nullable=True),
        sa.Column("last_snapshot_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_snapshot_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_snapshot_reason", sa.String(length=64), nullable=True),
        sa.Column("last_command_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_command_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_result_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result_event_id", sa.String(length=255), nullable=True),
        sa.Column("last_heartbeat_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_report_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", name="uq_node_transport_state_node"),
    )


def downgrade() -> None:
    op.drop_table("node_transport_state")
    op.drop_index("ix_node_transport_event_log_node_type", table_name="node_transport_event_log")
    op.drop_index("ix_node_transport_event_log_node_id", table_name="node_transport_event_log")
    op.drop_table("node_transport_event_log")
    op.drop_index("ix_node_transport_outbox_status_retry", table_name="node_transport_outbox")
    op.drop_index("ix_node_transport_outbox_aggregate_id", table_name="node_transport_outbox")
    op.drop_index("ix_node_transport_outbox_node_id", table_name="node_transport_outbox")
    op.drop_table("node_transport_outbox")
