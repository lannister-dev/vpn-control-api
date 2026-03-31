"""create billing tables

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-03-27 12:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_order',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_id', sa.Uuid(), sa.ForeignKey('plan.id', ondelete='SET NULL'), nullable=True),
        sa.Column('amount_rub', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('provider', sa.String(16), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('external_id', sa.String(256), nullable=False, unique=True),
        sa.Column('payment_url', sa.Text(), nullable=True),
        sa.Column('provider_meta', sa.Text(), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('subscription_id', sa.Uuid(), sa.ForeignKey('subscription.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_payment_order_user_id', 'payment_order', ['user_id'])
    op.create_index('ix_payment_order_status', 'payment_order', ['status'])
    op.create_index('ix_payment_order_provider', 'payment_order', ['provider'])
    op.create_index('ix_payment_order_expires_at', 'payment_order', ['expires_at'])

    op.create_table(
        'balance_transaction',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('type', sa.String(32), nullable=False),
        sa.Column('order_id', sa.Uuid(), sa.ForeignKey('payment_order.id', ondelete='SET NULL'), nullable=True),
        sa.Column('description', sa.String(256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_balance_transaction_user_id', 'balance_transaction', ['user_id'])
    op.create_index('ix_balance_transaction_type', 'balance_transaction', ['type'])
    op.create_index('ix_balance_transaction_created_at', 'balance_transaction', ['created_at'])


def downgrade() -> None:
    op.drop_table('balance_transaction')
    op.drop_table('payment_order')
