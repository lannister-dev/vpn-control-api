from decimal import Decimal

from sqlalchemy import BIGINT, Numeric
from sqlalchemy.orm import mapped_column, Mapped, relationship

from shared.database.base_model import Base


class User(Base):
    __tablename__ = "user"

    telegram_id: Mapped[int] = mapped_column(BIGINT, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    keys: Mapped[list["VpnKey"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )