"""add zone reference table and FK from vpn_node.zone

Creates a small lookup table mapping zone codes (europe/america/asia) to
human-readable name + emoji used for subscription display in Happ. Adds an
FK from vpn_node.zone to zone.code (nullable, ON DELETE SET NULL) so admins
can classify nodes through the UI without free-text typos.

Revision ID: e1a2b3c4d5f6
Revises: d7f3a9b5c8e1
Create Date: 2026-04-20
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "e1a2b3c4d5f6"
down_revision: Union[str, None] = "d7f3a9b5c8e1"
branch_labels = None
depends_on = None


SEED_ZONES = [
    ("europe", "Europe", "🇪🇺", 10),
    ("americas", "Americas", "🌎", 20),
    ("asia", "Asia", "🌏", 30),
    ("oceania", "Oceania", "🇦🇺", 40),
    ("africa", "Africa", "🌍", 50),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("zone"):
        op.create_table(
            "zone",
            sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("code", sa.String(16), nullable=False),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("emoji", sa.String(16), nullable=False, server_default=sa.text("''")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_zone_code"),
        )
        op.create_index("ix_zone_code", "zone", ["code"], unique=True)

    for code, name, emoji, sort_order in SEED_ZONES:
        op.execute(
            sa.text(
                "INSERT INTO zone (code, name, emoji, sort_order) "
                "VALUES (:code, :name, :emoji, :sort_order) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, name=name, emoji=emoji, sort_order=sort_order)
        )

    op.execute(
        "UPDATE vpn_node SET zone = NULL "
        "WHERE zone IS NOT NULL "
        "AND zone NOT IN (SELECT code FROM zone)"
    )

    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("vpn_node")}
    if "fk_vpn_node_zone_zone_code" not in existing_fks:
        op.create_foreign_key(
            "fk_vpn_node_zone_zone_code",
            "vpn_node",
            "zone",
            ["zone"],
            ["code"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("vpn_node")}
    if "fk_vpn_node_zone_zone_code" in existing_fks:
        op.drop_constraint("fk_vpn_node_zone_zone_code", "vpn_node", type_="foreignkey")

    if inspector.has_table("zone"):
        op.drop_index("ix_zone_code", table_name="zone")
        op.drop_table("zone")
