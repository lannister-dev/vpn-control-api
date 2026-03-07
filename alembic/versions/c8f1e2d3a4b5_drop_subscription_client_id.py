"""drop subscription.client_id legacy column

Revision ID: c8f1e2d3a4b5
Revises: ab12c3d4e5f6
Create Date: 2026-02-28
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c8f1e2d3a4b5"
down_revision: Union[str, None] = "ab12c3d4e5f6"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_subscription_client_id", table_name="subscription")
    op.drop_column("subscription", "client_id")


def downgrade() -> None:
    op.add_column(
        "subscription",
        sa.Column("client_id", sa.UUID(), nullable=True),
    )
    op.create_index("ix_subscription_client_id", "subscription", ["client_id"], unique=False)
