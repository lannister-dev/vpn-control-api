import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base_model import Base


class RecurringExpenseTemplate(Base):
    __tablename__ = "recurring_expense_template"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="RUB", server_default=text("'RUB'"), nullable=False
    )
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    vendor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_recurring_expense_template_next_run_at", "next_run_at"),
    )


class Expense(Base):
    __tablename__ = "expense"

    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="RUB", server_default=text("'RUB'"), nullable=False
    )
    amount_rub: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    incurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    vendor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recurring_expense_template.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_expense_kind", "kind"),
        Index("ix_expense_incurred_at", "incurred_at"),
        Index("ix_expense_template_id", "template_id"),
    )
