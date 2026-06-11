"""add payment_provider_fee table and order fee/net columns

Revision ID: d4e8f1a6c302
Revises: c7a1f5b9d234
Create Date: 2026-06-09

"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "d4e8f1a6c302"
down_revision = "c7a1f5b9d234"
branch_labels = None
depends_on = None

_SEED_RATES = (
    ("platega", 2, "11.0000"),
    ("platega", 13, "5.0000"),
)


def upgrade() -> None:
    op.add_column(
        "payment_order", sa.Column("fee_rub", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "payment_order", sa.Column("net_rub", sa.Numeric(10, 2), nullable=True)
    )

    op.create_table(
        "payment_provider_fee",
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("payment_method", sa.Integer(), nullable=True),
        sa.Column("fee_percent", sa.Numeric(6, 4), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_payment_provider_fee_method",
        "payment_provider_fee",
        ["provider", "payment_method"],
        unique=True,
        postgresql_where=sa.text("payment_method IS NOT NULL"),
    )
    op.create_index(
        "uq_payment_provider_fee_default",
        "payment_provider_fee",
        ["provider"],
        unique=True,
        postgresql_where=sa.text("payment_method IS NULL"),
    )

    _seed_rates()
    _backfill_order_fees()


def _seed_rates() -> None:
    bind = op.get_bind()
    for provider, method, percent in _SEED_RATES:
        bind.execute(
            sa.text(
                "INSERT INTO payment_provider_fee "
                "(id, provider, payment_method, fee_percent, created_at, updated_at, is_active) "
                "VALUES (:id, :provider, :method, :percent, now(), now(), true)"
            ),
            {
                "id": uuid.uuid4(),
                "provider": provider,
                "method": method,
                "percent": percent,
            },
        )


def _backfill_order_fees() -> None:
    bind = op.get_bind()
    for _provider, method, percent in _SEED_RATES:
        fraction = float(percent) / 100.0
        bind.execute(
            sa.text(
                "UPDATE payment_order "
                "SET fee_rub = round(amount_rub * :fraction, 2), "
                "    net_rub = amount_rub - round(amount_rub * :fraction, 2) "
                "WHERE provider = 'platega' "
                "  AND status IN ('paid', 'completed') "
                "  AND fee_rub IS NULL "
                "  AND provider_meta IS NOT NULL "
                "  AND (provider_meta::jsonb ->> 'paymentMethod') = :method"
            ),
            {"fraction": fraction, "method": str(method)},
        )


def downgrade() -> None:
    op.drop_index("uq_payment_provider_fee_default", table_name="payment_provider_fee")
    op.drop_index("uq_payment_provider_fee_method", table_name="payment_provider_fee")
    op.drop_table("payment_provider_fee")
    op.drop_column("payment_order", "net_rub")
    op.drop_column("payment_order", "fee_rub")
