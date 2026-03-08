import secrets
from uuid import UUID

from fastapi import Header, Depends, HTTPException, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status

from services.auth.utils import AuthUtils
from services.config import get_settings
from services.nodes.models import VpnNode
from services.nodes.service import VpnNodeService, get_vpn_node_service
from shared.monitoring.metrics import AUTH_ATTEMPT_TOTAL


node_bearer = HTTPBearer(auto_error=False)

async def node_auth(
    x_node_id: str | None = Header(default=None, alias="X-Node-ID"),
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

    if x_agent_instance_id is None:
        AUTH_ATTEMPT_TOTAL.labels(type="node", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Agent-Instance-ID header required",
        )

    raw_token = credentials.credentials.strip()
    token_hash = AuthUtils.hash_node_token(raw_token)

    if x_node_id:
        node = await service.vpn_node_repository.get_by_id(x_node_id)
        if node is not None:
            identity = await service.node_agent_identity_repository.get_by_node_and_instance(
                node_id=node.id,
                agent_instance_id=x_agent_instance_id,
            )
            if identity is not None and secrets.compare_digest(identity.auth_token_hash, token_hash):
                AUTH_ATTEMPT_TOTAL.labels(type="node", result="success").inc()
                return node

    identity = await service.node_agent_identity_repository.get_by_instance_and_token_hash(
        agent_instance_id=x_agent_instance_id,
        token_hash=token_hash,
    )
    if identity is None:
        AUTH_ATTEMPT_TOTAL.labels(type="node", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node token",
        )

    node = await service.vpn_node_repository.get_by_id(identity.node_id)
    if node is None:
        AUTH_ATTEMPT_TOTAL.labels(type="node", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node token",
        )

    AUTH_ATTEMPT_TOTAL.labels(type="node", result="success").inc()
    return node

async def _admin_auth_session(request) -> bool:
    """Try session cookie auth. Returns True if valid."""
    from services.auth.admin.constants import SESSION_COOKIE_NAME
    from services.auth.admin.crypto import hash_session_id

    settings = get_settings()
    if not settings.admin_auth.enabled:
        return False

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return False

    from services.auth.admin.service import AdminAuthService
    from shared.database.session import AsyncDatabase

    session_hash = hash_session_id(session_id)
    async with AsyncDatabase.get_session_maker()() as db_session:
        svc = AdminAuthService(db_session)
        result = await svc.validate_session(session_hash)
        return result is not None


async def admin_auth(
        request: Request,
) -> None:
    """
    Validates admin access using admin session cookie only.
    """
    if await _admin_auth_session(request):
        AUTH_ATTEMPT_TOTAL.labels(type="admin", result="success").inc()
        return

    AUTH_ATTEMPT_TOTAL.labels(type="admin", result="failure").inc()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired admin session",
    )


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
