"""merge referral and user delete heads

Revision ID: d8e9f0a1b2c3
Revises: c1d2e3f4a5b6, f1a2b3c4d5e6
Create Date: 2026-04-11 15:25:00.000000
"""

from typing import Sequence, Union


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = ("c1d2e3f4a5b6", "f1a2b3c4d5e6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
