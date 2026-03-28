from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.billing.models import BalanceTransaction, PaymentOrder
from shared.database.base_repository import BaseRepository


class OrderRepository(BaseRepository[PaymentOrder]):
    def __init__(self, session: AsyncSession):
        super().__init__(PaymentOrder, session)

    async def get_by_external_id(self, external_id: str) -> PaymentOrder | None:
        result = await self.session.execute(
            select(PaymentOrder).where(PaymentOrder.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[PaymentOrder], int]:
        base = select(PaymentOrder).where(PaymentOrder.user_id == user_id)
        total = (
            await self.session.execute(
                select(func.count(PaymentOrder.id)).where(
                    PaymentOrder.user_id == user_id
                )
            )
        ).scalar() or 0
        rows = (
            await self.session.execute(
                base.order_by(PaymentOrder.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), total

    async def list_by_status(self, status: str) -> list[PaymentOrder]:
        result = await self.session.execute(
            select(PaymentOrder).where(PaymentOrder.status == status)
        )
        return list(result.scalars().all())


class TransactionRepository(BaseRepository[BalanceTransaction]):
    def __init__(self, session: AsyncSession):
        super().__init__(BalanceTransaction, session)

    async def list_by_user(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[BalanceTransaction], int]:
        base = select(BalanceTransaction).where(
            BalanceTransaction.user_id == user_id
        )
        total = (
            await self.session.execute(
                select(func.count(BalanceTransaction.id)).where(
                    BalanceTransaction.user_id == user_id
                )
            )
        ).scalar() or 0
        rows = (
            await self.session.execute(
                base.order_by(BalanceTransaction.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), total
