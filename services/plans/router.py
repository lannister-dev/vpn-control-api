from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.auth.dependencies import admin_auth
from services.plans.exceptions import PlanAlreadyExists, PlanNotFound
from services.plans.schemas import (
    PlanCreateIn,
    PlanListOut,
    PlanOut,
    PlanUpdateIn,
)
from services.plans.service import PlanService, get_plan_service

router = APIRouter(prefix="/plans", tags=["Plans"], dependencies=[Depends(admin_auth)])


@router.get("", response_model=PlanListOut, summary="List all plans")
async def list_plans(
    active_only: bool = Query(False, description="Show only active plans"),
    service: PlanService = Depends(get_plan_service),
):
    return await service.list_plans(active_only=active_only)


@router.get("/{plan_id}", response_model=PlanOut, summary="Get plan by ID")
async def get_plan(
    plan_id: UUID,
    service: PlanService = Depends(get_plan_service),
):
    try:
        return await service.get_plan(plan_id)
    except PlanNotFound:
        raise HTTPException(status_code=404, detail="Plan not found")


@router.post(
    "",
    response_model=PlanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create plan",
)
async def create_plan(
    data: PlanCreateIn,
    service: PlanService = Depends(get_plan_service),
):
    try:
        return await service.create_plan(data)
    except PlanAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/{plan_id}", response_model=PlanOut, summary="Update plan")
async def update_plan(
    plan_id: UUID,
    data: PlanUpdateIn,
    service: PlanService = Depends(get_plan_service),
):
    try:
        return await service.update_plan(plan_id, data)
    except PlanNotFound:
        raise HTTPException(status_code=404, detail="Plan not found")
    except PlanAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/{plan_id}", response_model=PlanOut, summary="Deactivate plan (soft-delete)")
async def delete_plan(
    plan_id: UUID,
    service: PlanService = Depends(get_plan_service),
):
    try:
        return await service.delete_plan(plan_id)
    except PlanNotFound:
        raise HTTPException(status_code=404, detail="Plan not found")
