from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from services.finance.schemas import (
    ExpenseCreateIn,
    ExpenseKindEnum,
    RecurringPeriodEnum,
    RecurringTemplateCreateIn,
)
from services.finance.service import FinanceService, _add_months, _normalize_to_rub


def _row(**overrides):
    base = dict(
        id=uuid4(),
        kind="infrastructure",
        amount=Decimal("40.00"),
        currency="RUB",
        amount_rub=Decimal("40.00"),
        fx_rate=None,
        incurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        period_start=None,
        period_end=None,
        vendor=None,
        region=None,
        description=None,
        template_id=None,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture()
def service():
    svc = FinanceService(AsyncMock())
    svc.expense_repo = AsyncMock()
    svc.template_repo = AsyncMock()
    svc.order_repo = AsyncMock()
    return svc


class TestNormalize:
    def test_rub_passthrough(self):
        assert _normalize_to_rub(Decimal("199.00"), "RUB", None) == Decimal("199.00")

    def test_eur_uses_fx(self):
        assert _normalize_to_rub(Decimal("40.00"), "EUR", Decimal("100")) == Decimal(
            "4000.00"
        )

    def test_non_rub_without_fx_raises(self):
        with pytest.raises(ValueError):
            _normalize_to_rub(Decimal("40.00"), "EUR", None)

    def test_add_months_clamps_day(self):
        assert _add_months(
            datetime(2026, 1, 31, tzinfo=timezone.utc), 1
        ) == datetime(2026, 2, 28, tzinfo=timezone.utc)


class TestCreateExpense:
    async def test_eur_expense_normalized_to_rub(self, service):
        service.expense_repo.create = AsyncMock(
            return_value=_row(currency="EUR", amount_rub=Decimal("4000.00"))
        )
        data = ExpenseCreateIn(
            kind=ExpenseKindEnum.INFRASTRUCTURE,
            amount=Decimal("40.00"),
            currency="eur",
            fx_rate=Decimal("100"),
            incurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        await service.create_expense(data)

        payload = service.expense_repo.create.await_args.args[0]
        assert payload["currency"] == "EUR"
        assert payload["kind"] == "infrastructure"
        assert payload["amount_rub"] == Decimal("4000.00")


class TestMaterialize:
    async def test_monthly_catchup_creates_one_per_period(self, service):
        tpl = SimpleNamespace(
            id=uuid4(),
            kind="infrastructure",
            amount=Decimal("40.00"),
            currency="EUR",
            fx_rate=Decimal("100"),
            period="monthly",
            next_run_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
            vendor="Hetzner",
            region="eu",
            description="node",
        )
        service.template_repo.list_due = AsyncMock(return_value=[tpl])
        service.expense_repo.create = AsyncMock()
        service.template_repo.update_by_id = AsyncMock()

        now = datetime(2026, 6, 10, tzinfo=timezone.utc)
        created = await service.materialize_due_templates(now)

        assert created == 3
        first_payload = service.expense_repo.create.await_args_list[0].args[0]
        assert first_payload["amount_rub"] == Decimal("4000.00")
        assert first_payload["template_id"] == tpl.id
        advanced = service.template_repo.update_by_id.await_args.args[1]["next_run_at"]
        assert advanced == datetime(2026, 7, 10, tzinfo=timezone.utc)


class TestOverview:
    async def test_pl_math_and_waterfall(self, service):
        service.order_repo.revenue_totals = AsyncMock(
            side_effect=[(1000.0, 100.0, 5), (800.0, 80.0, 4)]
        )
        service.expense_repo.total = AsyncMock(side_effect=[300.0, 250.0])
        service.order_repo.revenue_daily = AsyncMock(
            return_value=[("2026-06-01", 1000.0, 100.0)]
        )
        service.expense_repo.daily = AsyncMock(return_value=[("2026-06-01", 300.0)])
        service.expense_repo.summary_by_kind = AsyncMock(
            return_value=[("infrastructure", 200.0, 3), ("marketing", 100.0, 1)]
        )

        out = await service.overview(
            datetime(2026, 5, 11, tzinfo=timezone.utc),
            datetime(2026, 6, 10, tzinfo=timezone.utc),
        )

        assert out.gross.value == 1000.0
        assert out.net.value == 900.0
        assert out.expenses.value == 300.0
        assert out.profit.value == 600.0
        assert out.margin.value == 60.0
        assert out.profit.tone == "up"
        assert out.expenses.tone == "down"  # higher expenses = bad
        assert out.waterfall[0].key == "gross" and out.waterfall[0].value == 1000.0
        assert out.waterfall[1].key == "commissions" and out.waterfall[1].value == -100.0
        assert out.waterfall[-1].key == "profit" and out.waterfall[-1].value == 600.0
        assert out.daily[0].profit == 600.0


class TestIncome:
    async def test_breakdowns_and_uncaptured(self, service):
        service.order_repo.revenue_by = AsyncMock(
            side_effect=[
                [("platega", 1000.0)],
                [("plan_purchase", 1000.0)],
                [(1, 1000.0)],
            ]
        )
        service.order_repo.topup_total = AsyncMock(return_value=500.0)
        service.order_repo.uncaptured_commission = AsyncMock(return_value=(900.0, 90.0))
        order = SimpleNamespace(
            id=uuid4(),
            paid_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
            provider="platega",
            order_type="plan_purchase",
            period_months=1,
            amount_rub=Decimal("199.00"),
            fee_rub=Decimal("22.00"),
            net_rub=Decimal("177.00"),
            status="completed",
        )
        service.order_repo.recent_revenue_orders = AsyncMock(
            return_value=[(order, "@user", 123)]
        )

        out = await service.income(
            datetime(2026, 5, 11, tzinfo=timezone.utc),
            datetime(2026, 6, 10, tzinfo=timezone.utc),
        )

        assert out.by_provider[0].key == "platega"
        assert out.by_period[0].key == "1"
        assert out.topup_volume == 500.0
        assert out.uncaptured_pct == 10.0
        assert out.transactions[0].user == "@user"
        assert out.transactions[0].is_top_up is False


class TestMetrics:
    async def test_unit_economics(self, service):
        service._mrr_and_paying = AsyncMock(return_value=(10000.0, 50))
        service.order_repo.new_paying_users = AsyncMock(return_value=10)
        service.expense_repo.total_by_kinds = AsyncMock(return_value=13400.0)

        with patch("services.finance.service.SubscriptionRepository") as SR:
            inst = SR.return_value
            inst.count_stats = AsyncMock(return_value=(100, 60, 10))
            inst.count_stats_at = AsyncMock(return_value=(100, 60, 10))
            out = await service.metrics()

        assert out.arpu == 200.0
        assert out.arr == 120000.0
        assert out.cac == 1340.0
        assert out.churn_rate == 20.0
        assert round(out.ltv) == 1000
        assert out.ltv_cac == 0.75
        assert len(out.mrr_series) == 12


class TestCreateTemplate:
    async def test_template_enums_serialized(self, service):
        service.template_repo.create = AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(),
                name="Hetzner node",
                kind="infrastructure",
                amount=Decimal("40.00"),
                currency="EUR",
                fx_rate=Decimal("100"),
                period="monthly",
                next_run_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                vendor="Hetzner",
                region="eu",
                description=None,
                is_active=True,
                created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )
        )
        data = RecurringTemplateCreateIn(
            name="Hetzner node",
            kind=ExpenseKindEnum.INFRASTRUCTURE,
            amount=Decimal("40.00"),
            currency="EUR",
            fx_rate=Decimal("100"),
            period=RecurringPeriodEnum.MONTHLY,
            next_run_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await service.create_template(data)

        payload = service.template_repo.create.await_args.args[0]
        assert payload["kind"] == "infrastructure"
        assert payload["period"] == "monthly"
        assert payload["currency"] == "EUR"
