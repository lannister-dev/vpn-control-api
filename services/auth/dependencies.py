import secrets

from fastapi import Header, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status

from services.auth.utils import AuthUtils
from services.config import get_settings
from services.nodes.models import VpnNode
from services.nodes.repository import get_vpn_node_repository, VpnNodeRepository


async def node_auth(
    x_node_id: str = Header(..., alias="X-Node-ID"),
    authorization: str = Header(...),
    repository: VpnNodeRepository = Depends(get_vpn_node_repository)
) -> VpnNode:
    """
        Auth dependency for NodeAgent (machine-to-machine).

        Requirements:
        - Authorization: Bearer <token>
        - X-Node-ID: <uuid>

        Returns:
            VpnNode — authenticated node instance
        """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )
    raw_token = authorization.removeprefix("Bearer ").strip()
    token_hash = AuthUtils.hash_node_token(raw_token)

    node = await repository.get_by_id(x_node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Node not found",
        )
    if node.auth_token_hash != token_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node token",
        )

    return node

admin_bearer = HTTPBearer(auto_error=False)

async def admin_auth(
    credentials: HTTPAuthorizationCredentials = Depends(admin_bearer),
) -> None:
    """
    Validates admin access using a static Bearer API key.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )
    raw_token = credentials.credentials
    expected_hash = get_settings().admin.api_key_hash
    provided_hash = AuthUtils.hash_admin_api_key(raw_token)

    if not secrets.compare_digest(provided_hash, expected_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )
