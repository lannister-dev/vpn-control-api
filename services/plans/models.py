from sqlalchemy import BigInteger, String, Integer, text
from sqlalchemy.orm import mapped_column, Mapped

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
