"""merge route entry and probe signal heads

Revision ID: d46f956272de
Revises: b6c1d2e3f4a5, a0f7c2d4e9b1
Create Date: 2026-03-24 01:55:17.349812

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd46f956272de'
down_revision: Union[str, None] = ('b6c1d2e3f4a5', 'a0f7c2d4e9b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
