from uuid import UUID

from fastapi import APIRouter, Depends
from starlette import status

from services.users.repository import get_user_repository, UserRepository
from services.vpn.keys.repository import VpnKeyRepository, get_vpn_key_repository, KeyAssignmentRepository, \
    get_key_assignment_repository
from services.vpn.keys.schemas import VpnKeyCreate, VpnKeyOut, KeyAssignmentCreate
from services.vpn.keys.service import VpnService

router = APIRouter(prefix="/vpn", tags=["VPN"])


@router.post(
    "",
    response_model=VpnKeyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_vpn_key(
        payload: VpnKeyCreate,
        vpn_key_repository: VpnKeyRepository = Depends(get_vpn_key_repository),
        user_repository: UserRepository = Depends(get_user_repository)
):
    return await VpnService.create_key(payload, vpn_key_repository, user_repository)


@router.post("/keys/{key_id}/assign", status_code=status.HTTP_201_CREATED)
async def assign_key_to_node(
        key_id: UUID,
        payload: KeyAssignmentCreate,
        key_repository: VpnKeyRepository = Depends(get_vpn_key_repository),
        assignment_repository: KeyAssignmentRepository = Depends(get_key_assignment_repository)
):
    await VpnService.assign_key(key_id, payload, key_repository, assignment_repository)

    return {"status": "assigned"}


@router.post("/keys/{key_id}/revoke")
async def revoke_key(
        key_id: UUID,
        key_repository: VpnKeyRepository = Depends(get_vpn_key_repository),
        assignment_repository: KeyAssignmentRepository = Depends(get_key_assignment_repository)
):
    await VpnService.revoke_key(key_id, key_repository, assignment_repository)

    return {"status": "revoked"}
