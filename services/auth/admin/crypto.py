from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Any

try:
    import jwt
    from jwt import PyJWKClient
except ModuleNotFoundError:  # pragma: no cover
    jwt = None
    PyJWKClient = None

from services.auth.admin.constants import SALT_BYTES, SESSION_ID_BYTES


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def generate_session_id() -> str:
    return secrets.token_hex(SESSION_ID_BYTES)


def hash_session_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_hex(16)


def generate_pkce_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def generate_pkce_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_telegram_oidc_id_token(
    *,
    id_token: str,
    client_id: str,
    jwks_url: str,
    issuer: str,
    expected_nonce: str | None = None,
) -> dict[str, Any] | None:
    if jwt is None or PyJWKClient is None:
        return None
    try:
        jwk_client = PyJWKClient(jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except Exception:
        return None

    if expected_nonce:
        token_nonce = payload.get("nonce")
        if not token_nonce or not hmac.compare_digest(str(token_nonce), expected_nonce):
            return None

    return payload
