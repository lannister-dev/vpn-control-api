"""harden node agent identity rotation

Revision ID: 4f8a1d2c3b4e
Revises: 2b3c4d5e6f70
Create Date: 2026-03-11
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4f8a1d2c3b4e"
down_revision: Union[str, None] = "2b3c4d5e6f70"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.add_column(
        "node_agent_identity",
        sa.Column("prev_auth_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "node_agent_identity",
        sa.Column("prev_auth_token_valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "node_agent_identity",
        sa.Column(
            "full_resync_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "node_agent_identity",
        sa.Column("last_bootstrap_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_node_agent_identity_prev_auth_token_hash",
        "node_agent_identity",
        ["prev_auth_token_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_node_agent_identity_prev_auth_token_hash",
        table_name="node_agent_identity",
    )
    op.drop_column("node_agent_identity", "last_bootstrap_at")
    op.drop_column("node_agent_identity", "full_resync_required")
    op.drop_column("node_agent_identity", "prev_auth_token_valid_until")
    op.drop_column("node_agent_identity", "prev_auth_token_hash")
