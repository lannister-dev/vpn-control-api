from fastapi import APIRouter, Depends, status

from services.admin_audit.service import AdminAuditService, get_admin_audit_service
from services.admin_ops.schemas import AdminSetRouteHealthIn
from services.auth.dependencies import admin_auth, current_admin_actor
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
        actor: str = Depends(current_admin_actor),
        placement_service: UserPlacementService = Depends(get_user_placement_service),
        audit: AdminAuditService = Depends(get_admin_audit_service),
) -> PlacementMigrateBackendOut:
    result = await placement_service.migrate_backend(payload)
    await audit.record(
        actor=actor,
        action="migrate_backend",
        target=str(payload.source_backend_id),
        summary=f"migrated {result.migrated_count} placements from {payload.source_backend_id}",
        details={
            "source_backend_id": str(payload.source_backend_id),
            "target_backend_id": str(payload.target_backend_id) if payload.target_backend_id else None,
            "reason": payload.last_migration_reason,
            "migrated_count": result.migrated_count,
        },
    )
    return result


@router.post(
    "/set-route-health",
    response_model=RouteOut,
    status_code=status.HTTP_200_OK,
    summary="Set route health state by route id",
)
async def admin_set_route_health(
        payload: AdminSetRouteHealthIn,
        actor: str = Depends(current_admin_actor),
        route_service: RouteService = Depends(get_route_service),
        audit: AdminAuditService = Depends(get_admin_audit_service),
) -> RouteOut:
    result = await route_service.update_route_health(
        payload.route_id,
        RouteHealthUpdateIn(
            action=payload.action,
            cooldown_hours=payload.cooldown_hours,
        ),
    )
    await audit.record(
        actor=actor,
        action="set_route_health",
        target=str(payload.route_id),
        summary=f"route {result.name} → {payload.action}",
        details={
            "route_id": str(payload.route_id),
            "route_name": result.name,
            "action": payload.action,
            "cooldown_hours": payload.cooldown_hours,
            "new_status": str(result.health_status),
        },
    )
    return result
