"""add route entry node

Revision ID: b6c1d2e3f4a5
Revises: e1c7b9a4d2f6
Create Date: 2026-03-22

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b6c1d2e3f4a5"
down_revision = "e1c7b9a4d2f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("route", sa.Column("entry_node_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_route_entry_node_id_vpn_node",
        "route",
        "vpn_node",
        ["entry_node_id"],
        ["id"],
    )
    op.create_index("ix_route_entry_node_id", "route", ["entry_node_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_route_entry_node_id", table_name="route")
    op.drop_constraint("fk_route_entry_node_id_vpn_node", "route", type_="foreignkey")
    op.drop_column("route", "entry_node_id")
