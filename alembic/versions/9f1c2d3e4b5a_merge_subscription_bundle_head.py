"""merge subscription bundle head

Revision ID: 9f1c2d3e4b5a
Revises: 46e5de9c2a28, 7b5f3c2a9d10
Create Date: 2026-03-15

"""

from typing import Sequence, Union


revision: str = "9f1c2d3e4b5a"
down_revision: Union[str, Sequence[str], None] = ("46e5de9c2a28", "7b5f3c2a9d10")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
