from fastapi import APIRouter, Depends, status

from services.auth.dependencies import connect_auth
from services.connect.schemas import (
    ConnectRouteSetIn,
    ConnectRouteSetOut,
    ConnectTelemetryIn,
    ConnectTelemetryOut,
)
from services.connect.service import ConnectService, get_connect_service
from services.connect.telemetry_service import ConnectTelemetryService, get_connect_telemetry_service

router = APIRouter(prefix="/connect", tags=["Connect"])


@router.post(
    "",
    response_model=ConnectRouteSetOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(connect_auth)],
    summary="Resolve user connect routeset",
)
async def connect_routeset(
        payload: ConnectRouteSetIn,
        service: ConnectService = Depends(get_connect_service),
):
    return await service.connect_routeset(payload)


@router.post(
    "/telemetry",
    response_model=ConnectTelemetryOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(connect_auth)],
    summary="Ingest client route telemetry and apply route health policy",
)
async def connect_telemetry(
        payload: ConnectTelemetryIn,
        service: ConnectTelemetryService = Depends(get_connect_telemetry_service),
):
    return await service.report(payload)
