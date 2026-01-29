from uuid import UUID
from fastapi import APIRouter, Depends
from starlette import status
from services.vpn.keys.schemas import VpnKeyCreate, VpnKeyOut, KeyAssignmentCreate
from services.vpn.keys.service import VpnKeyService, get_vpn_key_service

router = APIRouter(prefix="/vpn", tags=["VPN"])


@router.post(
    "",
    response_model=VpnKeyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_vpn_key(
        payload: VpnKeyCreate,
        service: VpnKeyService = Depends(get_vpn_key_service)
):
    return await service.create_key(payload)


@router.post("/keys/{key_id}/assign", status_code=status.HTTP_201_CREATED)
async def assign_key_to_node(
        key_id: UUID,
        payload: KeyAssignmentCreate,
        service: VpnKeyService = Depends(get_vpn_key_service)
):
    await service.assign_key(key_id, payload)

    return {"status": "assigned"}


@router.post("/keys/{key_id}/revoke")
async def revoke_key(
        key_id: UUID,
       service: VpnKeyService = Depends(get_vpn_key_service)
):
    await service.revoke_key(key_id)

    return {"status": "revoked"}
