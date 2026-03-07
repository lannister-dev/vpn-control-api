"""add vpn_key traffic counters

Revision ID: 1a2b3c4d5e6f
Revises: e7b4a2c9d1f0
Create Date: 2026-03-07
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, None] = "e7b4a2c9d1f0"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vpn_key",
        sa.Column(
            "used_traffic_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "vpn_key",
        sa.Column(
            "last_reported_total_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("vpn_key", "last_reported_total_bytes")
    op.drop_column("vpn_key", "used_traffic_bytes")
