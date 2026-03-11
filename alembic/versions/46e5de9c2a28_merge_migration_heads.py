"""merge migration heads

Revision ID: 46e5de9c2a28
Revises: 3c4d5e6f7a81, 4f8a1d2c3b4e
Create Date: 2026-03-12 01:32:55.333207

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46e5de9c2a28'
down_revision: Union[str, None] = ('3c4d5e6f7a81', '4f8a1d2c3b4e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
