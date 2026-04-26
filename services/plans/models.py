from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

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
