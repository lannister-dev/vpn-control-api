"""drop legacy subscription_device vpn_key_id

Revision ID: e1c7b9a4d2f6
Revises: d4e5f6a7b8c9
Create Date: 2026-03-22

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1c7b9a4d2f6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_subscription_device_vpn_key_id", table_name="subscription_device")
    op.drop_column("subscription_device", "vpn_key_id")


def downgrade() -> None:
    op.add_column("subscription_device", sa.Column("vpn_key_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_subscription_device_vpn_key_id_vpn_key",
        "subscription_device",
        "vpn_key",
        ["vpn_key_id"],
        ["id"],
    )
    op.execute(
        sa.text(
            """
            WITH ranked_keys AS (
                SELECT
                    sdk.subscription_device_id,
                    sdk.vpn_key_id,
                    row_number() OVER (
                        PARTITION BY sdk.subscription_device_id
                        ORDER BY sdk.is_primary DESC, sdk.created_at ASC, sdk.id ASC
                    ) AS rn
                FROM subscription_device_key AS sdk
                WHERE sdk.is_active = true
            )
            UPDATE subscription_device AS sd
            SET vpn_key_id = rk.vpn_key_id
            FROM ranked_keys AS rk
            WHERE sd.id = rk.subscription_device_id
              AND rk.rn = 1
            """
        )
    )
    op.alter_column("subscription_device", "vpn_key_id", nullable=False)
    op.create_index(
        "ix_subscription_device_vpn_key_id",
        "subscription_device",
        ["vpn_key_id"],
        unique=False,
    )
