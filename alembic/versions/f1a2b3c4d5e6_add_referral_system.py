"""add referral system

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-04-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # User: referral_code
    op.add_column(
        'user',
        sa.Column('referral_code', sa.String(12), nullable=True),
    )
    op.create_index('ix_user_referral_code', 'user', ['referral_code'], unique=True)

    # Referral table
    op.create_table(
        'referral',
        sa.Column('id', sa.Uuid(), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column('referrer_user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('referred_user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('reward_amount', sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
        sa.Column('referred_reward_amount', sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
        sa.Column('rewarded_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_referral_referrer_user_id', 'referral', ['referrer_user_id'])
    op.create_index('ix_referral_status', 'referral', ['status'])
    op.create_unique_constraint('uq_referral_referred_user', 'referral', ['referred_user_id'])

    # BalanceTransaction: add referral type support (no schema change needed,
    # type is a free-form string)


def downgrade() -> None:
    op.drop_constraint('uq_referral_referred_user', 'referral', type_='unique')
    op.drop_index('ix_referral_status', table_name='referral')
    op.drop_index('ix_referral_referrer_user_id', table_name='referral')
    op.drop_table('referral')
    op.drop_index('ix_user_referral_code', table_name='user')
    op.drop_column('user', 'referral_code')
