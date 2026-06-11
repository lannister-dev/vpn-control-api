from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from services.billing.constants import (
    NON_GATEWAY_PROVIDERS,
    REVENUE_ORDER_STATUSES,
)
from services.billing.models import (
    BalanceTransaction,
    PaymentOrder,
    PaymentProviderFee,
)
from services.billing.schemas import OrderTypeEnum
from services.users.models import User
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

    # ── Analytics aggregations (revenue = paid/completed, excl. top_up) ──

    @staticmethod
    def _revenue_where(date_from: datetime | None, date_to: datetime | None):
        conds = [
            PaymentOrder.status.in_(REVENUE_ORDER_STATUSES),
            PaymentOrder.order_type != OrderTypeEnum.TOP_UP,
        ]
        if date_from is not None:
            conds.append(PaymentOrder.paid_at >= date_from)
        if date_to is not None:
            conds.append(PaymentOrder.paid_at < date_to)
        return conds

    async def revenue_totals(
        self, date_from: datetime | None, date_to: datetime | None
    ) -> tuple[float, float, int]:
        row = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(PaymentOrder.amount_rub), 0),
                    func.coalesce(func.sum(PaymentOrder.fee_rub), 0),
                    func.count(PaymentOrder.id),
                ).where(*self._revenue_where(date_from, date_to))
            )
        ).one()
        return float(row[0]), float(row[1]), int(row[2])

    async def revenue_daily(
        self, date_from: datetime | None, date_to: datetime | None
    ) -> list[tuple[str, float, float]]:
        day = func.date(PaymentOrder.paid_at)
        rows = await self.session.execute(
            select(
                day,
                func.coalesce(func.sum(PaymentOrder.amount_rub), 0),
                func.coalesce(func.sum(PaymentOrder.fee_rub), 0),
            )
            .where(*self._revenue_where(date_from, date_to))
            .group_by(day)
            .order_by(day)
        )
        return [(str(r[0]), float(r[1]), float(r[2])) for r in rows.all()]

    async def revenue_by(
        self, column, date_from: datetime | None, date_to: datetime | None
    ) -> list[tuple[object, float]]:
        rows = await self.session.execute(
            select(column, func.coalesce(func.sum(PaymentOrder.amount_rub), 0))
            .where(*self._revenue_where(date_from, date_to))
            .group_by(column)
            .order_by(func.sum(PaymentOrder.amount_rub).desc())
        )
        return [(r[0], float(r[1])) for r in rows.all()]

    async def topup_total(
        self, date_from: datetime | None, date_to: datetime | None
    ) -> float:
        conds = [
            PaymentOrder.status.in_(REVENUE_ORDER_STATUSES),
            PaymentOrder.order_type == OrderTypeEnum.TOP_UP,
        ]
        if date_from is not None:
            conds.append(PaymentOrder.paid_at >= date_from)
        if date_to is not None:
            conds.append(PaymentOrder.paid_at < date_to)
        row = await self.session.execute(
            select(func.coalesce(func.sum(PaymentOrder.amount_rub), 0)).where(*conds)
        )
        return float(row.scalar() or 0)

    async def uncaptured_commission(
        self, date_from: datetime | None, date_to: datetime | None
    ) -> tuple[float, float]:
        row = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(PaymentOrder.amount_rub), 0),
                    func.coalesce(
                        func.sum(
                            case(
                                (PaymentOrder.fee_rub.is_(None), PaymentOrder.amount_rub),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(
                    *self._revenue_where(date_from, date_to),
                    PaymentOrder.provider.notin_(NON_GATEWAY_PROVIDERS),
                )
            )
        ).one()
        return float(row[0]), float(row[1])

    async def new_paying_users(
        self, date_from: datetime, date_to: datetime
    ) -> int:
        first_paid = (
            select(
                PaymentOrder.user_id,
                func.min(PaymentOrder.paid_at).label("fp"),
            )
            .where(
                PaymentOrder.status.in_(REVENUE_ORDER_STATUSES),
                PaymentOrder.order_type != OrderTypeEnum.TOP_UP,
                PaymentOrder.paid_at.isnot(None),
            )
            .group_by(PaymentOrder.user_id)
            .subquery()
        )
        stmt = select(func.count()).select_from(first_paid).where(
            first_paid.c.fp >= date_from, first_paid.c.fp < date_to
        )
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def recent_revenue_orders(
        self, *, limit: int = 50
    ) -> list[tuple[PaymentOrder, str | None, int | None]]:
        rows = await self.session.execute(
            select(PaymentOrder, User.username, User.telegram_id)
            .join(User, User.id == PaymentOrder.user_id)
            .where(PaymentOrder.status.in_(REVENUE_ORDER_STATUSES))
            .order_by(PaymentOrder.paid_at.desc().nullslast())
            .limit(limit)
        )
        return [(r[0], r[1], r[2]) for r in rows.all()]

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
