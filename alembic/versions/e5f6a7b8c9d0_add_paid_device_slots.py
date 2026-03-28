"""add paid device slots

Revision ID: e5f6a7b8c9d0
Revises: d5e6f7a8b9c0
Create Date: 2026-03-28 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Plan: included_devices, device_price_rub, device_price_stars
    op.add_column(
        'plan',
        sa.Column('included_devices', sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        'plan',
        sa.Column('device_price_rub', sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        'plan',
        sa.Column('device_price_stars', sa.Integer(), nullable=True),
    )

    # Subscription: paid_device_slots
    op.add_column(
        'subscription',
        sa.Column('paid_device_slots', sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    # PaymentOrder: order_type, device_slots_qty
    op.add_column(
        'payment_order',
        sa.Column('order_type', sa.String(24), nullable=False, server_default=sa.text("'plan_purchase'")),
    )
    op.add_column(
        'payment_order',
        sa.Column('device_slots_qty', sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index('ix_payment_order_order_type', 'payment_order', ['order_type'])

    # Backfill: existing active subscriptions with max_devices get paid_device_slots
    # so that included(1) + paid(N-1) = max_devices — no regression
    op.execute(
        sa.text(
            "UPDATE subscription SET paid_device_slots = COALESCE(max_devices, 5) - 1 "
            "WHERE is_active = true AND COALESCE(max_devices, 5) > 1"
        )
    )


def downgrade() -> None:
    op.drop_index('ix_payment_order_order_type', table_name='payment_order')
    op.drop_column('payment_order', 'device_slots_qty')
    op.drop_column('payment_order', 'order_type')
    op.drop_column('subscription', 'paid_device_slots')
    op.drop_column('plan', 'device_price_stars')
    op.drop_column('plan', 'device_price_rub')
    op.drop_column('plan', 'included_devices')
