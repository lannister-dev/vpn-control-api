from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.billing.models import PaymentOrder
from services.billing.repository import OrderRepository
from services.finance.constants import MATERIALIZE_CATCHUP_LIMIT
from services.finance.exceptions import ExpenseNotFound, TemplateNotFound
from services.finance.repository import (
    ExpenseRepository,
    RecurringExpenseTemplateRepository,
)
from services.finance.schemas import (
    BreakdownItemOut,
    DailyPointOut,
    ExpenseCreateIn,
    ExpenseKindSummaryOut,
    ExpenseListOut,
    ExpenseOut,
    ExpenseSummaryOut,
    ExpenseUpdateIn,
    IncomeOut,
    IncomeTxnOut,
    KpiOut,
    OverviewOut,
    RecurringTemplateCreateIn,
    RecurringTemplateListOut,
    RecurringTemplateOut,
    RecurringTemplateUpdateIn,
    WaterfallItemOut,
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
        self.order_repo = OrderRepository(session)

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

    # ── Analytics: Overview / Income ───────────────────────────

    @staticmethod
    def _kpi(cur: float, prev: float, *, higher_better: bool = True) -> KpiOut:
        delta = ((cur - prev) / prev * 100) if prev else None
        if delta is None or abs(delta) < 0.05:
            tone = "flat"
        else:
            good = delta > 0 if higher_better else delta < 0
            tone = "up" if good else "down"
        return KpiOut(
            value=cur,
            delta_pct=round(delta, 1) if delta is not None else None,
            tone=tone,
        )

    async def overview(self, date_from: datetime, date_to: datetime) -> OverviewOut:
        span = date_to - date_from
        prev_from, prev_to = date_from - span, date_from

        gross, fee, _ = await self.order_repo.revenue_totals(date_from, date_to)
        net = gross - fee
        exp = await self.expense_repo.total(date_from=date_from, date_to=date_to)
        profit = net - exp
        margin = (profit / gross * 100) if gross else 0.0

        pg, pf, _ = await self.order_repo.revenue_totals(prev_from, prev_to)
        pnet = pg - pf
        pexp = await self.expense_repo.total(date_from=prev_from, date_to=prev_to)
        pprofit = pnet - pexp
        pmargin = (pprofit / pg * 100) if pg else 0.0

        rev = {
            d: (g, f) for d, g, f in await self.order_repo.revenue_daily(date_from, date_to)
        }
        expd = dict(await self.expense_repo.daily(date_from=date_from, date_to=date_to))
        daily = []
        for d in sorted(set(rev) | set(expd)):
            g, f = rev.get(d, (0.0, 0.0))
            e = expd.get(d, 0.0)
            daily.append(
                DailyPointOut(date=d, income=g, commissions=f, expense=e, profit=g - f - e)
            )

        kinds = await self.expense_repo.summary_by_kind(
            date_from=date_from, date_to=date_to
        )
        waterfall = [
            WaterfallItemOut(key="gross", type="total", value=gross),
            WaterfallItemOut(key="commissions", type="neg", value=-fee),
        ]
        for kind, total_rub, _ in sorted(kinds, key=lambda r: float(r[1]), reverse=True):
            waterfall.append(
                WaterfallItemOut(key=kind, type="neg", value=-float(total_rub))
            )
        waterfall.append(WaterfallItemOut(key="profit", type="result", value=profit))

        return OverviewOut(
            gross=self._kpi(gross, pg),
            commissions=self._kpi(fee, pf, higher_better=False),
            net=self._kpi(net, pnet),
            expenses=self._kpi(exp, pexp, higher_better=False),
            profit=self._kpi(profit, pprofit),
            margin=self._kpi(margin, pmargin),
            daily=daily,
            waterfall=waterfall,
        )

    async def income(
        self, date_from: datetime, date_to: datetime, *, txn_limit: int = 50
    ) -> IncomeOut:
        by_provider = [
            BreakdownItemOut(key=str(k), value=v)
            for k, v in await self.order_repo.revenue_by(
                PaymentOrder.provider, date_from, date_to
            )
        ]
        by_type = [
            BreakdownItemOut(key=str(k), value=v)
            for k, v in await self.order_repo.revenue_by(
                PaymentOrder.order_type, date_from, date_to
            )
        ]
        by_period = [
            BreakdownItemOut(key=str(k), value=v)
            for k, v in await self.order_repo.revenue_by(
                PaymentOrder.period_months, date_from, date_to
            )
        ]
        topup = await self.order_repo.topup_total(date_from, date_to)
        gw_gross, gw_unknown = await self.order_repo.uncaptured_commission(
            date_from, date_to
        )
        uncaptured = (gw_unknown / gw_gross * 100) if gw_gross else 0.0

        rows = await self.order_repo.recent_revenue_orders(limit=txn_limit)
        txns = [
            IncomeTxnOut(
                id=order.id,
                paid_at=order.paid_at,
                user=username or (str(telegram_id) if telegram_id else None),
                provider=order.provider,
                order_type=order.order_type,
                period_months=order.period_months,
                amount_rub=order.amount_rub,
                fee_rub=order.fee_rub,
                net_rub=order.net_rub,
                status=order.status,
                is_top_up=order.order_type == "top_up",
            )
            for order, username, telegram_id in rows
        ]

        return IncomeOut(
            by_provider=by_provider,
            by_order_type=by_type,
            by_period=by_period,
            topup_volume=topup,
            uncaptured_pct=round(uncaptured, 1),
            transactions=txns,
        )

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
