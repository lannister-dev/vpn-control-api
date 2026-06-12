from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from services.auth.dependencies import admin_auth
from services.finance.exceptions import ExpenseNotFound, TemplateNotFound
from services.finance.schemas import (
    ExpenseCreateIn,
    ExpenseKindEnum,
    ExpenseListOut,
    ExpenseOut,
    ExpenseSummaryOut,
    ExpenseUpdateIn,
    IncomeOut,
    MetricsOut,
    OverviewOut,
    RecurringTemplateCreateIn,
    RecurringTemplateListOut,
    RecurringTemplateOut,
    RecurringTemplateUpdateIn,
)
from services.finance.service import FinanceService, get_finance_service
from services.finance.utils import default_range

router = APIRouter(
    prefix="/finance", tags=["Finance"], dependencies=[Depends(admin_auth)]
)


# ── Analytics ──────────────────────────────────────────────

@router.get(
    "/overview",
    response_model=OverviewOut,
    summary="P&L overview: KPIs, daily series, profit waterfall",
)
async def finance_overview(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    service: FinanceService = Depends(get_finance_service),
):
    start, end = default_range(date_from, date_to)
    return await service.overview(start, end)


@router.get(
    "/income",
    response_model=IncomeOut,
    summary="Income breakdowns + recent transactions",
)
async def finance_income(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    service: FinanceService = Depends(get_finance_service),
):
    start, end = default_range(date_from, date_to)
    return await service.income(start, end, txn_limit=limit)


@router.get(
    "/metrics",
    response_model=MetricsOut,
    summary="Unit-economics: MRR/ARR/ARPU/churn/LTV/CAC + MRR series",
)
async def finance_metrics(
    service: FinanceService = Depends(get_finance_service),
):
    return await service.metrics()


# ── Expenses ───────────────────────────────────────────────

@router.post(
    "/expenses",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an expense record",
)
async def create_expense(
    data: ExpenseCreateIn,
    service: FinanceService = Depends(get_finance_service),
):
    return await service.create_expense(data)


@router.get(
    "/expenses",
    response_model=ExpenseListOut,
    summary="List expenses with optional date/kind filters",
)
async def list_expenses(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    kind: ExpenseKindEnum | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: FinanceService = Depends(get_finance_service),
):
    return await service.list_expenses(
        date_from=date_from,
        date_to=date_to,
        kind=kind.value if kind else None,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/expenses/summary",
    response_model=ExpenseSummaryOut,
    summary="Expense totals grouped by kind",
)
async def expense_summary(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    service: FinanceService = Depends(get_finance_service),
):
    return await service.expense_summary(date_from=date_from, date_to=date_to)


@router.patch(
    "/expenses/{expense_id}",
    response_model=ExpenseOut,
    summary="Update an expense record",
)
async def update_expense(
    expense_id: UUID,
    data: ExpenseUpdateIn,
    service: FinanceService = Depends(get_finance_service),
):
    try:
        return await service.update_expense(expense_id, data)
    except ExpenseNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an expense record",
)
async def delete_expense(
    expense_id: UUID,
    service: FinanceService = Depends(get_finance_service),
):
    try:
        await service.delete_expense(expense_id)
    except ExpenseNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Recurring expense templates ────────────────────────────

@router.post(
    "/expense-templates",
    response_model=RecurringTemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a recurring expense template",
)
async def create_template(
    data: RecurringTemplateCreateIn,
    service: FinanceService = Depends(get_finance_service),
):
    return await service.create_template(data)


@router.get(
    "/expense-templates",
    response_model=RecurringTemplateListOut,
    summary="List recurring expense templates",
)
async def list_templates(
    service: FinanceService = Depends(get_finance_service),
):
    return await service.list_templates()


@router.patch(
    "/expense-templates/{template_id}",
    response_model=RecurringTemplateOut,
    summary="Update a recurring expense template",
)
async def update_template(
    template_id: UUID,
    data: RecurringTemplateUpdateIn,
    service: FinanceService = Depends(get_finance_service),
):
    try:
        return await service.update_template(template_id, data)
    except TemplateNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/expense-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a recurring expense template",
)
async def delete_template(
    template_id: UUID,
    service: FinanceService = Depends(get_finance_service),
):
    try:
        await service.delete_template(template_id)
    except TemplateNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
