from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.finance.constants import MATERIALIZE_CATCHUP_LIMIT
from services.finance.exceptions import ExpenseNotFound, TemplateNotFound
from services.finance.repository import (
    ExpenseRepository,
    RecurringExpenseTemplateRepository,
)
from services.finance.schemas import (
    ExpenseCreateIn,
    ExpenseKindSummaryOut,
    ExpenseListOut,
    ExpenseOut,
    ExpenseSummaryOut,
    ExpenseUpdateIn,
    RecurringTemplateCreateIn,
    RecurringTemplateListOut,
    RecurringTemplateOut,
    RecurringTemplateUpdateIn,
)
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

log = StructuredLogger(logging.getLogger("finance"))


def _add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _advance(dt: datetime, period: str) -> datetime:
    if period == "weekly":
        return dt + timedelta(weeks=1)
    if period == "yearly":
        return _add_months(dt, 12)
    return _add_months(dt, 1)


def _normalize_to_rub(
    amount: Decimal, currency: str, fx_rate: Decimal | None
) -> Decimal:
    if currency.upper() == "RUB":
        return amount
    if fx_rate is None or fx_rate <= 0:
        raise ValueError("fx_rate is required and must be > 0 for non-RUB currency")
    return (amount * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class FinanceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.expense_repo = ExpenseRepository(session)
        self.template_repo = RecurringExpenseTemplateRepository(session)

    # ── Expenses ───────────────────────────────────────────────

    async def create_expense(self, data: ExpenseCreateIn) -> ExpenseOut:
        payload = data.model_dump()
        payload["kind"] = data.kind.value
        payload["currency"] = payload["currency"].upper()
        payload["amount_rub"] = _normalize_to_rub(
            data.amount, payload["currency"], data.fx_rate
        )
        row = await self.expense_repo.create(payload)
        return ExpenseOut.model_validate(row)

    async def list_expenses(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ExpenseListOut:
        rows, total = await self.expense_repo.list_filtered(
            date_from=date_from, date_to=date_to, kind=kind, limit=limit, offset=offset
        )
        return ExpenseListOut(
            items=[ExpenseOut.model_validate(r) for r in rows], total=total
        )

    async def expense_summary(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ExpenseSummaryOut:
        rows = await self.expense_repo.summary_by_kind(
            date_from=date_from, date_to=date_to
        )
        items = [
            ExpenseKindSummaryOut(kind=k, total_rub=Decimal(str(s)), count=c)
            for k, s, c in rows
        ]
        total = sum((i.total_rub for i in items), Decimal("0"))
        return ExpenseSummaryOut(items=items, total_rub=total)

    async def update_expense(
        self, expense_id: UUID, data: ExpenseUpdateIn
    ) -> ExpenseOut:
        existing = await self.expense_repo.get_by_id(expense_id)
        if existing is None:
            raise ExpenseNotFound(f"Expense {expense_id} not found")

        patch = data.model_dump(exclude_unset=True)
        if "kind" in patch and patch["kind"] is not None:
            patch["kind"] = data.kind.value
        if "currency" in patch and patch["currency"] is not None:
            patch["currency"] = patch["currency"].upper()

        amount = patch.get("amount", existing.amount)
        currency = patch.get("currency", existing.currency)
        fx_rate = patch.get("fx_rate", existing.fx_rate)
        patch["amount_rub"] = _normalize_to_rub(amount, currency, fx_rate)

        row = await self.expense_repo.update_by_id(expense_id, patch)
        return ExpenseOut.model_validate(row)

    async def delete_expense(self, expense_id: UUID) -> None:
        existing = await self.expense_repo.get_by_id(expense_id)
        if existing is None:
            raise ExpenseNotFound(f"Expense {expense_id} not found")
        await self.expense_repo.delete_by_id(expense_id)

    # ── Recurring templates ────────────────────────────────────

    async def create_template(
        self, data: RecurringTemplateCreateIn
    ) -> RecurringTemplateOut:
        payload = data.model_dump()
        payload["kind"] = data.kind.value
        payload["period"] = data.period.value
        payload["currency"] = payload["currency"].upper()
        row = await self.template_repo.create(payload)
        return RecurringTemplateOut.model_validate(row)

    async def list_templates(self) -> RecurringTemplateListOut:
        rows = await self.template_repo.list_all()
        return RecurringTemplateListOut(
            items=[RecurringTemplateOut.model_validate(r) for r in rows]
        )

    async def update_template(
        self, template_id: UUID, data: RecurringTemplateUpdateIn
    ) -> RecurringTemplateOut:
        existing = await self.template_repo.get_by_id(template_id)
        if existing is None:
            raise TemplateNotFound(f"Template {template_id} not found")
        patch = data.model_dump(exclude_unset=True)
        if "kind" in patch and patch["kind"] is not None:
            patch["kind"] = data.kind.value
        if "period" in patch and patch["period"] is not None:
            patch["period"] = data.period.value
        if "currency" in patch and patch["currency"] is not None:
            patch["currency"] = patch["currency"].upper()
        row = await self.template_repo.update_by_id(template_id, patch)
        return RecurringTemplateOut.model_validate(row)

    async def delete_template(self, template_id: UUID) -> None:
        existing = await self.template_repo.get_by_id(template_id)
        if existing is None:
            raise TemplateNotFound(f"Template {template_id} not found")
        await self.template_repo.delete_by_id(template_id)

    # ── Materialization (called by reconciler) ─────────────────

    async def materialize_due_templates(self, now: datetime) -> int:
        due = await self.template_repo.list_due(now)
        created = 0
        for tpl in due:
            run_at = tpl.next_run_at
            guard = 0
            while run_at <= now and guard < MATERIALIZE_CATCHUP_LIMIT:
                await self.expense_repo.create(
                    {
                        "kind": tpl.kind,
                        "amount": tpl.amount,
                        "currency": tpl.currency,
                        "amount_rub": _normalize_to_rub(
                            tpl.amount, tpl.currency, tpl.fx_rate
                        ),
                        "fx_rate": tpl.fx_rate,
                        "incurred_at": run_at,
                        "vendor": tpl.vendor,
                        "region": tpl.region,
                        "description": tpl.description,
                        "template_id": tpl.id,
                    }
                )
                created += 1
                run_at = _advance(run_at, tpl.period)
                guard += 1
            await self.template_repo.update_by_id(tpl.id, {"next_run_at": run_at})
        return created


def get_finance_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> FinanceService:
    return FinanceService(session)
