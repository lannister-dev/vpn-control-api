from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.auth.dependencies import admin_auth
from services.zones.exceptions import ZoneAlreadyExists, ZoneNotFound
from services.zones.schemas import (
    ZoneCreateIn,
    ZoneListOut,
    ZoneOut,
    ZoneUpdateIn,
)
from services.zones.service import ZoneService, get_zone_service

router = APIRouter(prefix="/zones", tags=["Zones"], dependencies=[Depends(admin_auth)])


@router.get("", response_model=ZoneListOut, summary="List all zones")
async def list_zones(
    active_only: bool = Query(False, description="Show only active zones"),
    service: ZoneService = Depends(get_zone_service),
):
    return await service.list_zones(active_only=active_only)


@router.get("/{code}", response_model=ZoneOut, summary="Get zone by code")
async def get_zone(
    code: str,
    service: ZoneService = Depends(get_zone_service),
):
    try:
        return await service.get_zone(code)
    except ZoneNotFound:
        raise HTTPException(status_code=404, detail="Zone not found")


@router.post(
    "",
    response_model=ZoneOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create zone",
)
async def create_zone(
    data: ZoneCreateIn,
    service: ZoneService = Depends(get_zone_service),
):
    try:
        return await service.create_zone(data)
    except ZoneAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/{code}", response_model=ZoneOut, summary="Update zone")
async def update_zone(
    code: str,
    data: ZoneUpdateIn,
    service: ZoneService = Depends(get_zone_service),
):
    try:
        return await service.update_zone(code, data)
    except ZoneNotFound:
        raise HTTPException(status_code=404, detail="Zone not found")


@router.delete("/{code}", response_model=ZoneOut, summary="Deactivate zone (soft-delete)")
async def delete_zone(
    code: str,
    service: ZoneService = Depends(get_zone_service),
):
    try:
        return await service.delete_zone(code)
    except ZoneNotFound:
        raise HTTPException(status_code=404, detail="Zone not found")
