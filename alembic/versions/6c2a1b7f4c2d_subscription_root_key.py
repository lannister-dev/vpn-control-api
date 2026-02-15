"""subscription root vpn_key binding

Revision ID: 6c2a1b7f4c2d
Revises: 4f1d9a2b3a10
Create Date: 2026-02-15

"""

from alembic import op
import sqlalchemy as sa


revision = "6c2a1b7f4c2d"
down_revision = "4f1d9a2b3a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscription", sa.Column("root_vpn_key_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_subscription_root_vpn_key_id",
        "subscription",
        "vpn_key",
        ["root_vpn_key_id"],
        ["id"],
    )
    op.create_index("ix_subscription_root_vpn_key_id", "subscription", ["root_vpn_key_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_subscription_root_vpn_key_id", table_name="subscription")
    op.drop_constraint("fk_subscription_root_vpn_key_id", "subscription", type_="foreignkey")
    op.drop_column("subscription", "root_vpn_key_id")

