import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Header, Depends, HTTPException, Query, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status

from services.auth.utils import AuthUtils
from services.config import get_settings
from services.nodes.models import VpnNode
from services.nodes.auth_utils import identity_accepts_token
from services.nodes.service import VpnNodeService, get_vpn_node_service
from shared.monitoring.metrics import AUTH_ATTEMPT_TOTAL


node_bearer = HTTPBearer(auto_error=False)

async def node_auth(
    x_node_id: str | None = Header(default=None, alias="X-Node-ID"),
    x_agent_instance_id: UUID | None = Header(default=None, alias="X-Agent-Instance-ID"),
    credentials: HTTPAuthorizationCredentials | None = Security(node_bearer),
    service: VpnNodeService = Depends(get_vpn_node_service),
) -> VpnNode:
    now = datetime.now(timezone.utc)
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
            if identity is not None and identity_accepts_token(identity, token_hash, now=now):
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
    if not identity_accepts_token(identity, token_hash, now=now):
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


def _admin_auth_api_key(
    credentials: HTTPAuthorizationCredentials | None,
) -> bool:
    if credentials is None:
        return False

    if credentials.scheme.lower() != "bearer":
        return False

    raw_token = credentials.credentials.strip()
    if not raw_token:
        return False

    expected_hash = get_settings().admin.api_key_hash
    if not expected_hash:
        return False

    provided_hash = AuthUtils.hash_admin_api_key(raw_token)
    return secrets.compare_digest(provided_hash, expected_hash)


admin_bearer = HTTPBearer(auto_error=False)


async def admin_auth(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Security(admin_bearer),
) -> None:
    """
    Validates admin access using admin session cookie or bearer admin API key.
    """
    if await _admin_auth_session(request) or _admin_auth_api_key(credentials):
        AUTH_ATTEMPT_TOTAL.labels(type="admin", result="success").inc()
        return

    AUTH_ATTEMPT_TOTAL.labels(type="admin", result="failure").inc()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin credentials",
    )


async def current_admin_actor(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(admin_bearer),
) -> str:
    """Best-effort admin identity label for audit records.

    Returns:
        - username from session cookie when available
        - "api-key" when authenticated via bearer API key
        - "system" otherwise (auth disabled / anonymous)
    """
    from services.auth.admin.constants import SESSION_COOKIE_NAME
    from services.auth.admin.crypto import hash_session_id
    from services.auth.admin.service import AdminAuthService
    from shared.database.session import AsyncDatabase

    settings = get_settings()
    if settings.admin_auth.enabled:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if session_id:
            session_hash = hash_session_id(session_id)
            async with AsyncDatabase.get_session_maker()() as db_session:
                svc = AdminAuthService(db_session)
                result = await svc.validate_session(session_hash)
                if result is not None:
                    user, _session = result
                    return user.username

    if _admin_auth_api_key(credentials):
        return "api-key"

    return "system"


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


node_install_bearer = HTTPBearer(auto_error=False)


class NodeInstallCredentials:
    """Pair of (node, raw_token) returned by node_install_auth."""

    __slots__ = ("node", "raw_token")

    def __init__(self, node: VpnNode, raw_token: str) -> None:
        self.node = node
        self.raw_token = raw_token


async def node_install_auth(
        credentials: HTTPAuthorizationCredentials | None = Security(node_install_bearer),
        token: str | None = Query(default=None, description="Bootstrap token (alt to Bearer)"),
        service: VpnNodeService = Depends(get_vpn_node_service),
) -> NodeInstallCredentials:
    """
    Authenticates a pending VPN node's installer using its one-shot bootstrap token.

    Accepts token via either Authorization: Bearer <token> (preferred for JSON
    callbacks) or ?token=<token> query string (for the `curl | bash` installer).

    Rejects if the token is unknown, the node is inactive, the token has
    expired, or the node was already bootstrapped.
    """
    raw_token = None
    if credentials is not None and credentials.credentials:
        raw_token = credentials.credentials.strip()
    elif token:
        raw_token = token.strip()

    if not raw_token:
        AUTH_ATTEMPT_TOTAL.labels(type="node_install", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bootstrap token required",
        )

    token_hash = AuthUtils.hash_node_token(raw_token)
    node = await service.vpn_node_repository.get_by_auth_token_hash(token_hash)
    if node is None or not node.is_active:
        AUTH_ATTEMPT_TOTAL.labels(type="node_install", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bootstrap token",
        )

    if node.bootstrapped_at is not None:
        AUTH_ATTEMPT_TOTAL.labels(type="node_install", result="already_bootstrapped").inc()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node already bootstrapped; rotate token via admin API",
        )

    expires_at = node.bootstrap_token_expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            AUTH_ATTEMPT_TOTAL.labels(type="node_install", result="expired").inc()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bootstrap token expired",
            )

    AUTH_ATTEMPT_TOTAL.labels(type="node_install", result="success").inc()
    return NodeInstallCredentials(node=node, raw_token=raw_token)


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


relay_bearer = HTTPBearer(auto_error=False)


async def relay_auth(
        credentials: HTTPAuthorizationCredentials | None = Security(relay_bearer),
) -> None:
    """
    Validates the bearer token used by Go relay binaries to poll the entry backend pool.
    """
    if not credentials:
        AUTH_ATTEMPT_TOTAL.labels(type="relay", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if credentials.scheme.lower() != "bearer":
        AUTH_ATTEMPT_TOTAL.labels(type="relay", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    raw_token = credentials.credentials
    expected_token = get_settings().admin.relay_token
    if not expected_token:
        AUTH_ATTEMPT_TOTAL.labels(type="relay", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Relay auth not configured",
        )

    if not secrets.compare_digest(raw_token, expected_token):
        AUTH_ATTEMPT_TOTAL.labels(type="relay", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid relay token",
        )

    AUTH_ATTEMPT_TOTAL.labels(type="relay", result="success").inc()


bot_bearer = HTTPBearer(auto_error=False)


async def bot_auth(
        credentials: HTTPAuthorizationCredentials | None = Security(bot_bearer),
) -> None:
    """
    Validates Telegram bot access to bot-facing endpoints.
    """
    if not credentials:
        AUTH_ATTEMPT_TOTAL.labels(type="bot", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if credentials.scheme.lower() != "bearer":
        AUTH_ATTEMPT_TOTAL.labels(type="bot", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    raw_token = credentials.credentials
    expected_hash = get_settings().bot_api.api_key_hash
    provided_hash = AuthUtils.hash_admin_api_key(raw_token)

    if not expected_hash or not secrets.compare_digest(provided_hash, expected_hash):
        AUTH_ATTEMPT_TOTAL.labels(type="bot", result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bot token",
        )

    AUTH_ATTEMPT_TOTAL.labels(type="bot", result="success").inc()
