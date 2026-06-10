from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
