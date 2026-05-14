"""add device_model / platform / os_version to subscription_device

Captures Happ client headers (X-Device-Model, X-Device-Os, X-Ver-Os) so that
users see a meaningful device label ("iPhone 17 Pro / iOS 18.1") instead of
a raw User-Agent string. Pattern mirrors Remnawave's hwid_user_devices.

Revision ID: a1c5d3e9b7f2
Revises: f8a2c3b1d9e4
Create Date: 2026-05-14
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1c5d3e9b7f2"
down_revision: Union[str, None] = "f8a2c3b1d9e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_device",
        sa.Column("device_model", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "subscription_device",
        sa.Column("platform", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "subscription_device",
        sa.Column("os_version", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscription_device", "os_version")
    op.drop_column("subscription_device", "platform")
    op.drop_column("subscription_device", "device_model")
