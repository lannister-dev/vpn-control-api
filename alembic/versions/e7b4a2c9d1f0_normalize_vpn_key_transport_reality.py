"""normalize vpn_key.transport from tcp to reality

Revision ID: e7b4a2c9d1f0
Revises: d4a6c2f1b9e7
Create Date: 2026-03-01
"""

from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e7b4a2c9d1f0"
down_revision: Union[str, None] = "d4a6c2f1b9e7"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE vpn_key SET transport = 'reality' WHERE transport = 'tcp'")


def downgrade() -> None:
    op.execute("UPDATE vpn_key SET transport = 'tcp' WHERE transport = 'reality'")
