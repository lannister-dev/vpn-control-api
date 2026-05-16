"""subscription route assignment table

Revision ID: c8e2b1d4f7a3
Revises: a0f7c2d4e9b1
Create Date: 2026-05-16
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8e2b1d4f7a3"
down_revision: Union[str, None] = "a0f7c2d4e9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_route_assignment",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_device.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column(
            "entry_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vpn_node.id"),
            nullable=False,
        ),
        sa.Column(
            "backend_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vpn_node.id"),
            nullable=False,
        ),
        sa.Column(
            "route_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("route.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "last_assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "assignment_count",
            sa.BigInteger,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.UniqueConstraint(
            "subscription_id",
            "subscription_device_id",
            "transport",
            name="uq_route_assignment_sub_device_transport",
        ),
    )
    op.create_index(
        "ix_route_assignment_entry_node",
        "subscription_route_assignment",
        ["entry_node_id"],
    )
    op.create_index(
        "ix_route_assignment_backend_node",
        "subscription_route_assignment",
        ["backend_node_id"],
    )
    op.create_index(
        "ix_route_assignment_last_at",
        "subscription_route_assignment",
        [sa.text("last_assigned_at DESC")],
    )
    op.create_index(
        "ix_route_assignment_subscription",
        "subscription_route_assignment",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_route_assignment_subscription", table_name="subscription_route_assignment")
    op.drop_index("ix_route_assignment_last_at", table_name="subscription_route_assignment")
    op.drop_index("ix_route_assignment_backend_node", table_name="subscription_route_assignment")
    op.drop_index("ix_route_assignment_entry_node", table_name="subscription_route_assignment")
    op.drop_table("subscription_route_assignment")
