"""add version check constraints for placement and backend peer

Revision ID: f7b3c4d9e210
Revises: c2f94b9e1a11
Create Date: 2026-02-17

"""

from alembic import op


revision = "f7b3c4d9e210"
down_revision = "c2f94b9e1a11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_user_placement_op_version_ge_1",
        "user_placement",
        "op_version >= 1",
    )
    op.create_check_constraint(
        "ck_user_placement_applied_version_ge_0",
        "user_placement",
        "applied_version >= 0",
    )
    op.create_check_constraint(
        "ck_user_placement_applied_version_lte_op",
        "user_placement",
        "applied_version <= op_version",
    )

    op.create_check_constraint(
        "ck_backend_peer_op_version_ge_1",
        "backend_peer",
        "op_version >= 1",
    )
    op.create_check_constraint(
        "ck_backend_peer_applied_version_ge_0",
        "backend_peer",
        "applied_version >= 0",
    )
    op.create_check_constraint(
        "ck_backend_peer_applied_version_lte_op",
        "backend_peer",
        "applied_version <= op_version",
    )


def downgrade() -> None:
    op.drop_constraint("ck_backend_peer_applied_version_lte_op", "backend_peer", type_="check")
    op.drop_constraint("ck_backend_peer_applied_version_ge_0", "backend_peer", type_="check")
    op.drop_constraint("ck_backend_peer_op_version_ge_1", "backend_peer", type_="check")

    op.drop_constraint("ck_user_placement_applied_version_lte_op", "user_placement", type_="check")
    op.drop_constraint("ck_user_placement_applied_version_ge_0", "user_placement", type_="check")
    op.drop_constraint("ck_user_placement_op_version_ge_1", "user_placement", type_="check")

