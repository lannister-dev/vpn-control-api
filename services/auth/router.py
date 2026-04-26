from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from services.auth.utils import AuthUtils
from services.nodes.auth_utils import identity_accepts_token
from services.nodes.service import VpnNodeService, get_vpn_node_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/verify-node",
    summary="Verify node token",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Node verified"},
        400: {"description": "Invalid request"},
        401: {"description": "Invalid node token"},
        404: {"description": "Node not found"},
    },
)
async def verify_node_token(
    node_id: UUID,
    token: str,
    agent_instance_id: UUID,
    service: VpnNodeService = Depends(get_vpn_node_service),
):
    node = await service.vpn_node_repository.get_by_id(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    token_hash = AuthUtils.hash_node_token(token)
    identity = await service.node_agent_identity_repository.get_by_node_and_instance(
        node_id=node.id,
        agent_instance_id=agent_instance_id,
    )
    if identity is None or not identity_accepts_token(identity, token_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node token",
        )

    return None
