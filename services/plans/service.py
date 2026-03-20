from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.plans.exceptions import PlanAlreadyExists, PlanNotFound
from services.plans.repository import PlanRepository
from services.plans.schemas import (
    PlanCreateIn,
    PlanListOut,
    PlanOut,
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
        plan = await self.repo.create(data.model_dump())
        return PlanOut.model_validate(plan)

    async def update_plan(self, plan_id: UUID, data: PlanUpdateIn) -> PlanOut:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise PlanNotFound(f"Plan {plan_id} not found")

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return PlanOut.model_validate(plan)

        if "name" in update_data and update_data["name"] != plan.name:
            existing = await self.repo.get_by_name(update_data["name"])
            if existing:
                raise PlanAlreadyExists(
                    f"Plan with name '{update_data['name']}' already exists"
                )

        updated = await self.repo.update_by_id(plan_id, update_data)
        return PlanOut.model_validate(updated)

    async def delete_plan(self, plan_id: UUID) -> PlanOut:
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise PlanNotFound(f"Plan {plan_id} not found")
        updated = await self.repo.update_by_id(plan_id, {"is_active": False})
        return PlanOut.model_validate(updated)


def get_plan_service(session: AsyncSession = Depends(AsyncDatabase.get_session)) -> PlanService:
    return PlanService(session)
