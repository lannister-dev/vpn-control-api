from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from services.auth.utils import AuthUtils
from services.nodes.repository import get_vpn_node_repository, VpnNodeRepository

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/verify-node",
    summary="Verify node token",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def verify_node_token(
    node_id: str,
    token: str,
    repository: VpnNodeRepository = Depends(get_vpn_node_repository),
):
    node = await repository.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=401, detail="Node not found")

    if node.auth_token_hash != AuthUtils.hash_node_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")