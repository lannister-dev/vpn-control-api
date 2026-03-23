"""probe signal route scope

Revision ID: a0f7c2d4e9b1
Revises: e1c7b9a4d2f6
Create Date: 2026-03-22

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a0f7c2d4e9b1"
down_revision = "e1c7b9a4d2f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("probe_signal", sa.Column("route_id", sa.UUID(), nullable=True))
    op.add_column("probe_signal", sa.Column("transport_profile_id", sa.UUID(), nullable=True))
    op.add_column("probe_signal", sa.Column("transport_kind", sa.String(length=16), nullable=True))
    op.add_column(
        "probe_signal",
        sa.Column(
            "probe_kind",
            sa.String(length=32),
            nullable=False,
            server_default="tcp_connect",
        ),
    )
    op.add_column("probe_signal", sa.Column("target_host", sa.String(length=255), nullable=True))
    op.add_column("probe_signal", sa.Column("target_port", sa.Integer(), nullable=True))
    op.add_column("probe_signal", sa.Column("error_phase", sa.String(length=64), nullable=True))

    op.create_foreign_key(
        "fk_probe_signal_route_id_route",
        "probe_signal",
        "route",
        ["route_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_probe_signal_transport_profile_id_transport_profile",
        "probe_signal",
        "transport_profile",
        ["transport_profile_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_probe_signal_target_port_range",
        "probe_signal",
        "target_port IS NULL OR (target_port >= 1 AND target_port <= 65535)",
    )
    op.create_index("ix_probe_signal_route_id", "probe_signal", ["route_id"], unique=False)
    op.create_index(
        "ix_probe_signal_transport_profile_id",
        "probe_signal",
        ["transport_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_probe_signal_route_source_checked_at",
        "probe_signal",
        ["route_id", "source", "checked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_probe_signal_route_source_checked_at", table_name="probe_signal")
    op.drop_index("ix_probe_signal_transport_profile_id", table_name="probe_signal")
    op.drop_index("ix_probe_signal_route_id", table_name="probe_signal")
    op.drop_constraint("ck_probe_signal_target_port_range", "probe_signal", type_="check")
    op.drop_constraint(
        "fk_probe_signal_transport_profile_id_transport_profile",
        "probe_signal",
        type_="foreignkey",
    )
    op.drop_constraint("fk_probe_signal_route_id_route", "probe_signal", type_="foreignkey")
    op.drop_column("probe_signal", "error_phase")
    op.drop_column("probe_signal", "target_port")
    op.drop_column("probe_signal", "target_host")
    op.drop_column("probe_signal", "probe_kind")
    op.drop_column("probe_signal", "transport_kind")
    op.drop_column("probe_signal", "transport_profile_id")
    op.drop_column("probe_signal", "route_id")
