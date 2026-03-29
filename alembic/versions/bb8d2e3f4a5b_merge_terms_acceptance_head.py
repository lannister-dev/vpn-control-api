"""merge terms acceptance head

Revision ID: bb8d2e3f4a5b
Revises: aa7c1e2b3d4f, e5f6a7b8c9d0
Create Date: 2026-03-29 12:30:00.000000
"""

from typing import Sequence, Union


revision: str = "bb8d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = ("aa7c1e2b3d4f", "e5f6a7b8c9d0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
