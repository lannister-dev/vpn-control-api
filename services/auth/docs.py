import base64
import hashlib
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from services.config import get_settings

PROTECTED_PATHS = {"/api/instruction", "/api/openapi.json", "/api/instruction/oauth2-redirect"}


class DocsBasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path not in PROTECTED_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization")
        if auth and self._verify(auth):
            return await call_next(request)

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="instruction"'},
        )

    @staticmethod
    def _verify(auth_header: str) -> bool:
        if not auth_header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth_header[6:]).decode()
            username, _, password = decoded.partition(":")
        except Exception:
            return False

        cfg = get_settings().docs
        provided_hash = hashlib.sha256(password.encode()).hexdigest()

        return (
            secrets.compare_digest(username, cfg.username)
            and secrets.compare_digest(provided_hash, cfg.password_hash)
        )
