from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.base_model import Base


class Plan(Base):
    __tablename__ = "plan"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    traffic_limit_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )  # 0 = unlimited
    reset_strategy: Mapped[str] = mapped_column(
        String(16), default="NO_RESET", server_default=text("'NO_RESET'"), nullable=False
    )  # NO_RESET | MONTH | WEEK | DAY
    max_devices: Mapped[int] = mapped_column(
        Integer, default=5, server_default=text("5"), nullable=False
    )
    duration_days: Mapped[int] = mapped_column(
        Integer, default=30, server_default=text("30"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    whitelist_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    entry_relay_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    included_devices: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    price_rub: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=0, server_default=text("0"), nullable=False
    )
    device_price_rub: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=0, server_default=text("0"), nullable=False
    )
    price_stars: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
    )
    device_price_stars: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
    )

    periods: Mapped[list["PlanPeriod"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PlanPeriod.months",
    )


class PlanPeriod(Base):
    __tablename__ = "plan_period"

    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan.id", ondelete="CASCADE"), nullable=False
    )
    months: Mapped[int] = mapped_column(Integer, nullable=False)
    price_rub: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=0, server_default=text("0"), nullable=False
    )
    price_stars: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
    )

    plan: Mapped["Plan"] = relationship(back_populates="periods")

    __table_args__ = (
        UniqueConstraint("plan_id", "months", name="uq_plan_period_plan_months"),
    )
