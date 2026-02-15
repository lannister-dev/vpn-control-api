"""subscription hwid devices

Revision ID: 4f1d9a2b3a10
Revises: d03d1b2456b9
Create Date: 2026-02-15

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4f1d9a2b3a10"
down_revision = "d03d1b2456b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscription", sa.Column("hwid_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("subscription", sa.Column("max_devices", sa.Integer(), nullable=True))

    op.create_table(
        "subscription_device",
        sa.Column("subscription_id", sa.UUID(), nullable=False),
        sa.Column("hwid_hash", sa.String(length=64), nullable=False),
        sa.Column("vpn_key_id", sa.UUID(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscription.id"]),
        sa.ForeignKeyConstraint(["vpn_key_id"], ["vpn_key.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "hwid_hash", name="uq_subscription_device_hwid"),
    )
    op.create_index("ix_subscription_device_subscription_id", "subscription_device", ["subscription_id"], unique=False)
    op.create_index("ix_subscription_device_vpn_key_id", "subscription_device", ["vpn_key_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_subscription_device_vpn_key_id", table_name="subscription_device")
    op.drop_index("ix_subscription_device_subscription_id", table_name="subscription_device")
    op.drop_table("subscription_device")

    op.drop_column("subscription", "max_devices")
    op.drop_column("subscription", "hwid_enabled")

