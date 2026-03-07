from fastapi import APIRouter, Depends, status

from services.admin_ops.schemas import AdminSetRouteHealthIn
from services.auth.dependencies import admin_auth
from services.placements.schemas import PlacementMigrateBackendIn, PlacementMigrateBackendOut
from services.placements.service import UserPlacementService, get_user_placement_service
from services.routes.schemas import RouteHealthUpdateIn, RouteOut
from services.routes.service import RouteService, get_route_service

router = APIRouter(prefix="/admin", tags=["Admin Ops"], dependencies=[Depends(admin_auth)])


@router.post(
    "/migrate-backend",
    response_model=PlacementMigrateBackendOut,
    status_code=status.HTTP_200_OK,
    summary="Migrate active placements from source backend to target backend",
)
async def admin_migrate_backend(
        payload: PlacementMigrateBackendIn,
        placement_service: UserPlacementService = Depends(get_user_placement_service),
) -> PlacementMigrateBackendOut:
    return await placement_service.migrate_backend(payload)


@router.post(
    "/set-route-health",
    response_model=RouteOut,
    status_code=status.HTTP_200_OK,
    summary="Set route health state by route id",
)
async def admin_set_route_health(
        payload: AdminSetRouteHealthIn,
        route_service: RouteService = Depends(get_route_service),
) -> RouteOut:
    return await route_service.update_route_health(
        payload.route_id,
        RouteHealthUpdateIn(
            action=payload.action,
            cooldown_hours=payload.cooldown_hours,
        ),
    )
