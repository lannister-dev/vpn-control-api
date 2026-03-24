from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from services.auth.dependencies import admin_auth
from services.routes.schemas import (
    RouteCreateIn,
    RouteHealthUpdateIn,
    RouteOut,
    RouteUpdateIn,
    RouteWarmupTickOut,
    TransportProfileCreateIn,
    TransportProfileOut,
)
from services.routes.service import RouteService, get_route_service

router = APIRouter(prefix="/routes", tags=["Routes"])


@router.post(
    "/transport-profiles",
    response_model=TransportProfileOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_auth)],
    summary="Create transport profile",
)
async def create_transport_profile(
        payload: TransportProfileCreateIn,
        service: RouteService = Depends(get_route_service),
):
    return await service.create_transport_profile(payload)


@router.get(
    "/transport-profiles",
    response_model=list[TransportProfileOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="List active transport profiles",
)
async def list_transport_profiles(
        limit: int = Query(default=200, ge=1, le=2000),
        service: RouteService = Depends(get_route_service),
):
    return await service.list_transport_profiles(limit=limit)


@router.post(
    "",
    response_model=RouteOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_auth)],
    summary="Create route",
)
async def create_route(
        payload: RouteCreateIn,
        service: RouteService = Depends(get_route_service),
):
    return await service.create_route(payload)


@router.patch(
    "/{route_id}",
    response_model=RouteOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Update route",
)
async def update_route(
        route_id: UUID,
        payload: RouteUpdateIn,
        service: RouteService = Depends(get_route_service),
):
    return await service.update_route(route_id, payload)


@router.get(
    "",
    response_model=list[RouteOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="List active routes",
)
async def list_routes(
        node_id: UUID | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        service: RouteService = Depends(get_route_service),
):
    return await service.list_routes(node_id=node_id, limit=limit)


@router.post(
    "/{route_id}/health",
    response_model=RouteOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Update route health state",
)
async def update_route_health(
        route_id: UUID,
        payload: RouteHealthUpdateIn,
        service: RouteService = Depends(get_route_service),
):
    return await service.update_route_health(route_id, payload)


@router.post(
    "/admin/advance-warmup",
    response_model=RouteWarmupTickOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Advance route warmup stages",
)
async def advance_route_warmup(
        service: RouteService = Depends(get_route_service),
):
    return await service.advance_warmup()
