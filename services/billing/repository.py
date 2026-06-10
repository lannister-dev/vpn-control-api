from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from services.billing.models import (
    BalanceTransaction,
    PaymentOrder,
    PaymentProviderFee,
)
from shared.database.base_repository import BaseRepository


class OrderRepository(BaseRepository[PaymentOrder]):
    def __init__(self, session: AsyncSession):
        super().__init__(PaymentOrder, session)

    async def get_by_external_id(self, external_id: str) -> PaymentOrder | None:
        result = await self.session.execute(
            select(PaymentOrder).where(PaymentOrder.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id_for_update(
        self, external_id: str
    ) -> PaymentOrder | None:
        result = await self.session.execute(
            select(PaymentOrder)
            .where(PaymentOrder.external_id == external_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, order_id: UUID) -> PaymentOrder | None:
        result = await self.session.execute(
            select(PaymentOrder)
            .where(PaymentOrder.id == order_id)
            .with_for_update()
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

    async def has_completed_order_for_plan(self, user_id: UUID, plan_id: UUID) -> bool:
        result = await self.session.execute(
            select(func.count(PaymentOrder.id)).where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.plan_id == plan_id,
                PaymentOrder.status.in_(("paid", "completed")),
            )
        )
        return (result.scalar() or 0) > 0
    async def has_completed_paid_order(self, user_id: UUID) -> bool:
        result = await self.session.execute(
            select(func.count(PaymentOrder.id)).where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.status.in_(("paid", "completed")),
                PaymentOrder.amount_rub > 0,
            )
        )
        return (result.scalar() or 0) > 0

    async def get_last_paid_for_user(self, user_id: UUID) -> PaymentOrder | None:
        result = await self.session.execute(
            select(PaymentOrder)
            .where(PaymentOrder.user_id == user_id, PaymentOrder.status == "paid")
            .order_by(PaymentOrder.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_status(self, status: str) -> list[PaymentOrder]:
        result = await self.session.execute(
            select(PaymentOrder).where(PaymentOrder.status == status)
        )
        return list(result.scalars().all())

    async def bulk_expire_pending(self, *, now, limit: int = 500) -> int:
        expired_ids_stmt = (
            select(PaymentOrder.id)
            .where(
                PaymentOrder.status == "pending",
                PaymentOrder.expires_at.isnot(None),
                PaymentOrder.expires_at < now,
            )
            .order_by(PaymentOrder.expires_at.asc())
            .limit(limit)
        )
        rows = await self.session.execute(expired_ids_stmt)
        ids = list(rows.scalars().all())
        if not ids:
            return 0
        await self.session.execute(
            sa_update(PaymentOrder)
            .where(PaymentOrder.id.in_(ids))
            .values(status="expired", updated_at=now)
        )
        return len(ids)


class ProviderFeeRepository(BaseRepository[PaymentProviderFee]):
    def __init__(self, session: AsyncSession):
        super().__init__(PaymentProviderFee, session)

    async def list_all(self) -> list[PaymentProviderFee]:
        result = await self.session.execute(
            select(PaymentProviderFee).order_by(
                PaymentProviderFee.provider.asc(),
                PaymentProviderFee.payment_method.asc().nullsfirst(),
            )
        )
        return list(result.scalars().all())

    async def get_match(
        self, provider: str, payment_method: int | None
    ) -> PaymentProviderFee | None:
        result = await self.session.execute(
            select(PaymentProviderFee).where(
                PaymentProviderFee.provider == provider,
                PaymentProviderFee.payment_method.is_(None)
                if payment_method is None
                else PaymentProviderFee.payment_method == payment_method,
            )
        )
        return result.scalar_one_or_none()

    async def resolve(
        self, provider: str, payment_method: int | None
    ) -> PaymentProviderFee | None:
        if payment_method is not None:
            exact = await self.get_match(provider, payment_method)
            if exact is not None:
                return exact
        return await self.get_match(provider, None)


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
