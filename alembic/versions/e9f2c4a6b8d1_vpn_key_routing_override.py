"""vpn_key entry routing override

Adds nullable entry_routing_override_backend_tag column. When set, sing-box
publisher routes this key's user to the specified outbound regardless of
the default hash-based assignment.

Revision ID: e9f2c4a6b8d1
Revises: c5d8e2f4a9b3
Create Date: 2026-05-04
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "e9f2c4a6b8d1"
down_revision: Union[str, None] = "c5d8e2f4a9b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vpn_key",
        sa.Column(
            "entry_routing_override_backend_tag",
            sa.String(length=128),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("vpn_key", "entry_routing_override_backend_tag")
