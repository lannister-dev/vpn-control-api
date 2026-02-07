import secrets

from fastapi import Header, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status

from services.auth.utils import AuthUtils
from services.config import get_settings
from services.nodes.models import VpnNode
from services.nodes.service import VpnNodeService, get_vpn_node_service
from shared.metrics import AUTH_ATTEMPT_TOTAL


node_bearer = HTTPBearer(auto_error=False)

async def node_auth(
    x_node_id: str = Header(..., alias="X-Node-ID"),
    credentials: HTTPAuthorizationCredentials | None = Security(node_bearer),
    service: VpnNodeService = Depends(get_vpn_node_service),
) -> VpnNode:
    if credentials is None:
        AUTH_ATTEMPT_TOTAL.labels(type="node", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    raw_token = credentials.credentials.strip()
    token_hash = AuthUtils.hash_node_token(raw_token)

    node = await service.vpn_node_repository.get_by_id(x_node_id)
    if node is None:
        AUTH_ATTEMPT_TOTAL.labels(type="node", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    if node.auth_token_hash != token_hash:
        AUTH_ATTEMPT_TOTAL.labels(type="node", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node token",
        )

    AUTH_ATTEMPT_TOTAL.labels(type="node", result="success").inc()
    return node

admin_bearer = HTTPBearer(auto_error=False)

async def admin_auth(
        credentials: HTTPAuthorizationCredentials | None = Security(admin_bearer),
) -> None:
    """
    Validates admin access using a static Bearer API key.
    """
    if not credentials:
        AUTH_ATTEMPT_TOTAL.labels(type="admin", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if credentials.scheme.lower() != "bearer":
        AUTH_ATTEMPT_TOTAL.labels(type="admin", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )
    raw_token = credentials.credentials
    expected_hash = get_settings().admin.api_key_hash
    provided_hash = AuthUtils.hash_admin_api_key(raw_token)

    if not secrets.compare_digest(provided_hash, expected_hash):
        AUTH_ATTEMPT_TOTAL.labels(type="admin", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )

    AUTH_ATTEMPT_TOTAL.labels(type="admin", result="success").inc()
