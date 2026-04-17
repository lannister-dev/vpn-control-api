from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.plans.exceptions import PlanAlreadyExists, PlanNotFound
from services.plans.schemas import PlanCreateIn, PlanUpdateIn
from services.plans.service import PlanService


def _make_plan(
    *,
    name: str = "Basic",
    traffic_limit_bytes: int = 0,
    reset_strategy: str = "NO_RESET",
    max_devices: int = 5,
    included_devices: int = 1,
    duration_days: int = 30,
    sort_order: int = 0,
    is_active: bool = True,
    whitelist_enabled: bool = False,
    entry_relay_enabled: bool = False,
    price_rub: Decimal = Decimal("0"),
    device_price_rub: Decimal = Decimal("0"),
    price_stars: int | None = None,
    device_price_stars: int | None = None,
):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        description=None,
        traffic_limit_bytes=traffic_limit_bytes,
        reset_strategy=reset_strategy,
        max_devices=max_devices,
        included_devices=included_devices,
        duration_days=duration_days,
        sort_order=sort_order,
        is_active=is_active,
        whitelist_enabled=whitelist_enabled,
        entry_relay_enabled=entry_relay_enabled,
        price_rub=price_rub,
        device_price_rub=device_price_rub,
        price_stars=price_stars,
        device_price_stars=device_price_stars,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture()
def service(async_session):
    svc = PlanService(async_session)
    svc.repo = AsyncMock()
    return svc


class TestPlanServiceCreate:
    async def test_create_plan_success(self, service):
        service.repo.get_by_name.return_value = None
        plan = _make_plan(name="Pro", traffic_limit_bytes=10737418240)
        service.repo.create.return_value = plan

        data = PlanCreateIn(name="Pro", traffic_limit_bytes=10737418240)
        result = await service.create_plan(data)

        assert result.name == "Pro"
        assert result.traffic_limit_bytes == 10737418240
        service.repo.create.assert_awaited_once()

    async def test_create_plan_duplicate_name_raises(self, service):
        service.repo.get_by_name.return_value = _make_plan(name="Pro")

        with pytest.raises(PlanAlreadyExists):
            await service.create_plan(PlanCreateIn(name="Pro"))


class TestPlanServiceGet:
    async def test_get_plan_found(self, service):
        plan = _make_plan()
        service.repo.get_by_id.return_value = plan
        result = await service.get_plan(plan.id)
        assert result.id == plan.id

    async def test_get_plan_not_found_raises(self, service):
        service.repo.get_by_id.return_value = None
        with pytest.raises(PlanNotFound):
            await service.get_plan(uuid4())


class TestPlanServiceUpdate:
    async def test_update_plan_success(self, service):
        plan = _make_plan(name="Basic")
        updated = _make_plan(name="Premium")
        service.repo.get_by_id.return_value = plan
        service.repo.get_by_name.return_value = None
        service.repo.update_by_id.return_value = updated

        result = await service.update_plan(plan.id, PlanUpdateIn(name="Premium"))
        assert result.name == "Premium"

    async def test_update_plan_not_found_raises(self, service):
        service.repo.get_by_id.return_value = None
        with pytest.raises(PlanNotFound):
            await service.update_plan(uuid4(), PlanUpdateIn(name="X"))

    async def test_update_plan_empty_payload_returns_current(self, service):
        plan = _make_plan()
        service.repo.get_by_id.return_value = plan
        result = await service.update_plan(plan.id, PlanUpdateIn())
        assert result.id == plan.id
        service.repo.update_by_id.assert_not_awaited()


class TestPlanServiceDelete:
    async def test_delete_plan_soft_deletes(self, service):
        plan = _make_plan(is_active=True)
        deactivated = _make_plan(is_active=False)
        service.repo.get_by_id.return_value = plan
        service.repo.update_by_id.return_value = deactivated

        result = await service.delete_plan(plan.id)
        assert result.is_active is False
        service.repo.update_by_id.assert_awaited_once_with(plan.id, {"is_active": False})

    async def test_delete_plan_not_found_raises(self, service):
        service.repo.get_by_id.return_value = None
        with pytest.raises(PlanNotFound):
            await service.delete_plan(uuid4())


class TestPlanServiceValidation:
    def test_included_devices_le_max_devices(self):
        with pytest.raises(ValueError, match="included_devices must be <= max_devices"):
            PlanCreateIn(name="Bad", max_devices=3, included_devices=5)

    def test_included_devices_valid(self):
        plan = PlanCreateIn(name="OK", max_devices=5, included_devices=3)
        assert plan.included_devices == 3


class TestPlanServiceList:
    async def test_list_plans(self, service):
        plans = [_make_plan(name="A"), _make_plan(name="B")]
        service.repo.list_all.return_value = (plans, 2)

        result = await service.list_plans()
        assert result.total == 2
        assert len(result.items) == 2
