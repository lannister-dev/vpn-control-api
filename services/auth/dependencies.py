import secrets
from uuid import UUID

from fastapi import Header, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status

from services.auth.utils import AuthUtils
from services.config import get_settings
from services.nodes.models import VpnNode
from services.nodes.service import VpnNodeService, get_vpn_node_service
from shared.monitoring.metrics import AUTH_ATTEMPT_TOTAL


node_bearer = HTTPBearer(auto_error=False)

async def node_auth(
    x_node_id: str = Header(..., alias="X-Node-ID"),
    x_agent_instance_id: UUID | None = Header(default=None, alias="X-Agent-Instance-ID"),
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

    if x_agent_instance_id is None:
        AUTH_ATTEMPT_TOTAL.labels(type="node", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Agent-Instance-ID header required",
        )

    identity = await service.node_agent_identity_repository.get_by_node_and_instance(
        node_id=node.id,
        agent_instance_id=x_agent_instance_id,
    )
    if identity is None or not secrets.compare_digest(identity.auth_token_hash, token_hash):
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


connect_bearer = HTTPBearer(auto_error=False)


async def connect_auth(
        credentials: HTTPAuthorizationCredentials | None = Security(connect_bearer),
) -> None:
    """
    Validates app/client access to connect endpoints.
    """
    if not credentials:
        AUTH_ATTEMPT_TOTAL.labels(type="connect", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if credentials.scheme.lower() != "bearer":
        AUTH_ATTEMPT_TOTAL.labels(type="connect", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    raw_token = credentials.credentials
    expected_hash = get_settings().admin.connect_api_key_hash
    provided_hash = AuthUtils.hash_admin_api_key(raw_token)

    if not secrets.compare_digest(provided_hash, expected_hash):
        AUTH_ATTEMPT_TOTAL.labels(type="connect", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid connect token",
        )

    AUTH_ATTEMPT_TOTAL.labels(type="connect", result="success").inc()


bootstrap_bearer = HTTPBearer(auto_error=False)


async def bootstrap_auth(
        credentials: HTTPAuthorizationCredentials | None = Security(bootstrap_bearer),
) -> None:
    """
    Validates bootstrap token for node initial registration.
    """
    if not credentials:
        AUTH_ATTEMPT_TOTAL.labels(type="bootstrap", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    raw_token = credentials.credentials
    expected_hash = get_settings().admin.bootstrap_token_hash
    provided_hash = AuthUtils.hash_node_token(raw_token)

    if not secrets.compare_digest(provided_hash, expected_hash):
        AUTH_ATTEMPT_TOTAL.labels(type="bootstrap", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bootstrap token",
        )

    AUTH_ATTEMPT_TOTAL.labels(type="bootstrap", result="success").inc()


probe_bearer = HTTPBearer(auto_error=False)


async def probe_auth(
        credentials: HTTPAuthorizationCredentials | None = Security(probe_bearer),
) -> None:
    """
    Validates probe token for external probe result ingestion.
    """
    if not credentials:
        AUTH_ATTEMPT_TOTAL.labels(type="probe", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    raw_token = credentials.credentials
    expected_hash = get_settings().admin.probe_token_hash
    provided_hash = AuthUtils.hash_admin_api_key(raw_token)

    if not secrets.compare_digest(provided_hash, expected_hash):
        AUTH_ATTEMPT_TOTAL.labels(type="probe", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid probe token",
        )

    AUTH_ATTEMPT_TOTAL.labels(type="probe", result="success").inc()
