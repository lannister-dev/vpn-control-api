from uuid import UUID

from fastapi import Depends
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from services.plans.exceptions import PlanAlreadyExists, PlanNotFound
from services.plans.models import PlanPeriod
from services.plans.repository import PlanRepository
from services.plans.schemas import (
    PlanCreateIn,
    PlanListOut,
    PlanOut,
    PlanPeriodIn,
    PlanUpdateIn,
)
from shared.database.session import AsyncDatabase


class PlanService:
    def __init__(self, session: AsyncSession):
        self.repo = PlanRepository(session)

    async def list_plans(self, active_only: bool = False) -> PlanListOut:
        rows, total = await self.repo.list_all(active_only=active_only)
        return PlanListOut(
            items=[PlanOut.model_validate(p) for p in rows],
            total=total,
        )

    async def get_plan(self, plan_id: UUID) -> PlanOut:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise PlanNotFound(f"Plan {plan_id} not found")
        return PlanOut.model_validate(plan)

    async def create_plan(self, data: PlanCreateIn) -> PlanOut:
        existing = await self.repo.get_by_name(data.name)
        if existing:
            raise PlanAlreadyExists(f"Plan with name '{data.name}' already exists")

        periods = self._normalize_periods(data.periods, data.price_rub, data.price_stars)
        payload = data.model_dump(exclude={"periods"})
        self._apply_monthly_mirror(payload, periods)

        plan = await self.repo.create(payload)
        await self._replace_periods(plan.id, periods)
        refreshed = await self.repo.get_by_id(plan.id)
        return PlanOut.model_validate(refreshed)

    async def update_plan(self, plan_id: UUID, data: PlanUpdateIn) -> PlanOut:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise PlanNotFound(f"Plan {plan_id} not found")

        update_data = data.model_dump(exclude_unset=True, exclude={"periods"})

        if "name" in update_data and update_data["name"] != plan.name:
            existing = await self.repo.get_by_name(update_data["name"])
            if existing:
                raise PlanAlreadyExists(
                    f"Plan with name '{update_data['name']}' already exists"
                )

        if data.periods is not None:
            price_rub = update_data.get("price_rub", plan.price_rub)
            price_stars = update_data.get("price_stars", plan.price_stars)
            periods = self._normalize_periods(data.periods, price_rub, price_stars)
            self._apply_monthly_mirror(update_data, periods)
            await self._replace_periods(plan_id, periods)

        if update_data:
            await self.repo.update_by_id(plan_id, update_data)

        refreshed = await self.repo.get_by_id(plan_id)
        return PlanOut.model_validate(refreshed)

    @staticmethod
    def _normalize_periods(
        periods: list[PlanPeriodIn] | None, price_rub, price_stars: int | None,
    ) -> list[PlanPeriodIn]:
        result = list(periods) if periods else []
        if not any(p.months == 1 for p in result):
            result.append(
                PlanPeriodIn(months=1, price_rub=price_rub, price_stars=price_stars)
            )
        return sorted(result, key=lambda p: p.months)

    @staticmethod
    def _apply_monthly_mirror(payload: dict, periods: list[PlanPeriodIn]) -> None:
        monthly = next((p for p in periods if p.months == 1), None)
        if monthly is not None:
            payload["price_rub"] = monthly.price_rub
            payload["price_stars"] = monthly.price_stars

    async def _replace_periods(self, plan_id: UUID, periods: list[PlanPeriodIn]) -> None:
        session = self.repo.session
        await session.execute(
            delete(PlanPeriod).where(PlanPeriod.plan_id == plan_id)
        )
        for period in periods:
            session.add(
                PlanPeriod(
                    plan_id=plan_id,
                    months=period.months,
                    price_rub=period.price_rub,
                    price_stars=period.price_stars,
                )
            )
        await session.flush()

    async def delete_plan(self, plan_id: UUID) -> PlanOut:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise PlanNotFound(f"Plan {plan_id} not found")
        updated = await self.repo.update_by_id(plan_id, {"is_active": False})
        return PlanOut.model_validate(updated)


def get_plan_service(session: AsyncSession = Depends(AsyncDatabase.get_session)) -> PlanService:
    return PlanService(session)
