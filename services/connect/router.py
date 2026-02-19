from fastapi import APIRouter, Depends, status

from services.auth.dependencies import admin_auth
from services.connect.schemas import ConnectIn, ConnectOut
from services.connect.service import ConnectService, get_connect_service

router = APIRouter(prefix="/connect", tags=["Connect"])


@router.post(
    "",
    response_model=ConnectOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(admin_auth)],
    summary="Resolve user connect config via key + placement",
)
async def connect_user(
        payload: ConnectIn,
        service: ConnectService = Depends(get_connect_service),
):
    return await service.connect(payload)
