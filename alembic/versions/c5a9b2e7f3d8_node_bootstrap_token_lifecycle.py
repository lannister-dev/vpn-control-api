"""node bootstrap token lifecycle fields

Revision ID: c5a9b2e7f3d8
Revises: b7d1e4f9c2a3
Create Date: 2026-04-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c5a9b2e7f3d8"
down_revision: Union[str, Sequence[str], None] = "b7d1e4f9c2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vpn_node",
        sa.Column(
            "bootstrap_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "vpn_node",
        sa.Column(
            "bootstrapped_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("vpn_node", "bootstrapped_at")
    op.drop_column("vpn_node", "bootstrap_token_expires_at")
