"""add subscription device key bundle

Revision ID: 7b5f3c2a9d10
Revises: c6d91b2a4f31
Create Date: 2026-03-15

"""

import sqlalchemy as sa
from alembic import op
from uuid import uuid4


revision = "7b5f3c2a9d10"
down_revision = "c6d91b2a4f31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_device_key",
        sa.Column("subscription_device_id", sa.UUID(), nullable=False),
        sa.Column("vpn_key_id", sa.UUID(), nullable=False),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["subscription_device_id"], ["subscription_device.id"]),
        sa.ForeignKeyConstraint(["vpn_key_id"], ["vpn_key.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_device_id",
            "transport",
            name="uq_subscription_device_key_device_transport",
        ),
        sa.UniqueConstraint(
            "subscription_device_id",
            "vpn_key_id",
            name="uq_subscription_device_key_device_key",
        ),
    )
    op.create_index(
        "ix_subscription_device_key_device_id",
        "subscription_device_key",
        ["subscription_device_id"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_device_key_vpn_key_id",
        "subscription_device_key",
        ["vpn_key_id"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_device_key_transport",
        "subscription_device_key",
        ["transport"],
        unique=False,
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                sd.id AS subscription_device_id,
                sd.vpn_key_id AS vpn_key_id,
                vk.transport AS transport,
                sd.created_at AS created_at,
                sd.updated_at AS updated_at,
                sd.is_active AS is_active
            FROM subscription_device AS sd
            JOIN vpn_key AS vk ON vk.id = sd.vpn_key_id
            WHERE sd.vpn_key_id IS NOT NULL
            """
        )
    ).mappings().all()
    if rows:
        op.bulk_insert(
            sa.table(
                "subscription_device_key",
                sa.column("id", sa.UUID()),
                sa.column("subscription_device_id", sa.UUID()),
                sa.column("vpn_key_id", sa.UUID()),
                sa.column("transport", sa.String(length=16)),
                sa.column("is_primary", sa.Boolean()),
                sa.column("created_at", sa.DateTime(timezone=True)),
                sa.column("updated_at", sa.DateTime(timezone=True)),
                sa.column("is_active", sa.Boolean()),
            ),
            [
                {
                    "id": uuid4(),
                    "subscription_device_id": row["subscription_device_id"],
                    "vpn_key_id": row["vpn_key_id"],
                    "transport": row["transport"],
                    "is_primary": True,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "is_active": row["is_active"],
                }
                for row in rows
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_subscription_device_key_transport", table_name="subscription_device_key")
    op.drop_index("ix_subscription_device_key_vpn_key_id", table_name="subscription_device_key")
    op.drop_index("ix_subscription_device_key_device_id", table_name="subscription_device_key")
    op.drop_table("subscription_device_key")
