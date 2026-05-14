"""drop zone.fallback_entry_node_id

The xray/sing-box JSON fallback feature was reverted: subscription always
emits a plain vless URI list now and per-user failover happens server-side
(via probe-driven route filtering + UpstreamFailoverReconciler). The
fallback_entry_node_id column is dead config that misleads admins.

Revision ID: b2c4d6e8a1f3
Revises: a1c5d3e9b7f2
Create Date: 2026-05-15
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c4d6e8a1f3"
down_revision: Union[str, None] = "a1c5d3e9b7f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_zone_fallback_entry_node_id_vpn_node",
        "zone",
        type_="foreignkey",
    )
    op.drop_column("zone", "fallback_entry_node_id")


def downgrade() -> None:
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
