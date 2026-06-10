from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.finance.models import Expense, RecurringExpenseTemplate
from shared.database.base_repository import BaseRepository


class ExpenseRepository(BaseRepository[Expense]):
    def __init__(self, session: AsyncSession):
        super().__init__(Expense, session)

    @staticmethod
    def _apply_filters(stmt, *, date_from, date_to, kind):
        if date_from is not None:
            stmt = stmt.where(Expense.incurred_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Expense.incurred_at < date_to)
        if kind is not None:
            stmt = stmt.where(Expense.kind == kind)
        return stmt

    async def list_filtered(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Expense], int]:
        base = self._apply_filters(
            select(Expense), date_from=date_from, date_to=date_to, kind=kind
        )
        total = (
            await self.session.execute(
                self._apply_filters(
                    select(func.count(Expense.id)),
                    date_from=date_from,
                    date_to=date_to,
                    kind=kind,
                )
            )
        ).scalar() or 0
        rows = (
            await self.session.execute(
                base.order_by(Expense.incurred_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), total

    async def total(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> float:
        stmt = self._apply_filters(
            select(func.coalesce(func.sum(Expense.amount_rub), 0)),
            date_from=date_from,
            date_to=date_to,
            kind=None,
        )
        return float((await self.session.execute(stmt)).scalar() or 0)

    async def daily(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[tuple[str, float]]:
        day = func.date(Expense.incurred_at)
        stmt = self._apply_filters(
            select(day, func.coalesce(func.sum(Expense.amount_rub), 0)),
            date_from=date_from,
            date_to=date_to,
            kind=None,
        ).group_by(day).order_by(day)
        rows = await self.session.execute(stmt)
        return [(str(r[0]), float(r[1])) for r in rows.all()]

    async def total_by_kinds(
        self,
        kinds,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> float:
        stmt = select(func.coalesce(func.sum(Expense.amount_rub), 0)).where(
            Expense.kind.in_(kinds)
        )
        if date_from is not None:
            stmt = stmt.where(Expense.incurred_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Expense.incurred_at < date_to)
        return float((await self.session.execute(stmt)).scalar() or 0)

    async def summary_by_kind(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[tuple[str, float, int]]:
        stmt = self._apply_filters(
            select(
                Expense.kind,
                func.coalesce(func.sum(Expense.amount_rub), 0),
                func.count(Expense.id),
            ),
            date_from=date_from,
            date_to=date_to,
            kind=None,
        ).group_by(Expense.kind)
        rows = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in rows.all()]


class RecurringExpenseTemplateRepository(BaseRepository[RecurringExpenseTemplate]):
    def __init__(self, session: AsyncSession):
        super().__init__(RecurringExpenseTemplate, session)

    async def list_all(self) -> list[RecurringExpenseTemplate]:
        rows = await self.session.execute(
            select(RecurringExpenseTemplate).order_by(
                RecurringExpenseTemplate.next_run_at.asc()
            )
        )
        return list(rows.scalars().all())

    async def list_due(self, now: datetime) -> list[RecurringExpenseTemplate]:
        rows = await self.session.execute(
            select(RecurringExpenseTemplate)
            .where(
                RecurringExpenseTemplate.is_active.is_(True),
                RecurringExpenseTemplate.next_run_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        return list(rows.scalars().all())
