from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from services.auth.dependencies import admin_auth
from services.placements.schemas import (
    UserPlacementOut,
    UserPlacementUpsertIn,
)
from services.placements.service import UserPlacementService, get_user_placement_service

router = APIRouter(prefix="/placements", tags=["Placements"])


@router.post(
    "",
    response_model=UserPlacementOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_auth)],
    summary="Create or update placement (key -> backend node)",
)
async def upsert_placement(
        payload: UserPlacementUpsertIn,
        service: UserPlacementService = Depends(get_user_placement_service),
):
    return await service.upsert(payload)


@router.get(
    "",
    response_model=list[UserPlacementOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="List active placements",
)
async def list_placements(
        backend_node_id: UUID | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        service: UserPlacementService = Depends(get_user_placement_service),
):
    return await service.list_placements(
        backend_node_id=backend_node_id,
        limit=limit,
    )


@router.get(
    "/by-key/{key_id}",
    response_model=UserPlacementOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Get placement by key id",
)
async def get_placement_by_key(
        key_id: UUID,
        service: UserPlacementService = Depends(get_user_placement_service),
):
    return await service.get_by_key_id(key_id)
