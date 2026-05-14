"""add fallback_entry_node_id to zone

Adds a nullable FK pointing to vpn_node.id. Used by the subscription generator
to bundle a primary entry + fallback (whitelist) entry into a sing-box
`urltest` group, so the Happ client transparently fails over when the primary
gets DPI-blocked.

Revision ID: f8a2c3b1d9e4
Revises: e5f7a2b1c8d4
Create Date: 2026-05-14
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "f8a2c3b1d9e4"
down_revision: Union[str, None] = "e5f7a2b1c8d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "zone",
        sa.Column(
            "fallback_entry_node_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_zone_fallback_entry_node_id_vpn_node",
        "zone",
        "vpn_node",
        ["fallback_entry_node_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_zone_fallback_entry_node_id_vpn_node",
        "zone",
        type_="foreignkey",
    )
    op.drop_column("zone", "fallback_entry_node_id")
