from fastapi import APIRouter, Depends, status

from services.admin_status.schemas import AdminReadinessOut, AdminStatusOut
from services.admin_status.service import AdminStatusService, get_admin_status_service
from services.auth.dependencies import admin_auth

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/status",
    response_model=AdminStatusOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Get operational status snapshot",
)
async def get_admin_status(
        service: AdminStatusService = Depends(get_admin_status_service),
):
    return await service.get_status()


@router.get(
    "/readiness",
    response_model=AdminReadinessOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Get launch-readiness status",
)
async def get_admin_readiness(
        service: AdminStatusService = Depends(get_admin_status_service),
):
    return await service.get_readiness()
