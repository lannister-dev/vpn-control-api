from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from services.auth.dependencies import admin_auth
from services.auth.utils import AuthUtils


@pytest.mark.asyncio
async def test_admin_auth_accepts_valid_session_cookie():
    request = MagicMock()

    with patch("services.auth.dependencies._admin_auth_session", new=AsyncMock(return_value=True)):
        await admin_auth(request=request, credentials=None)


@pytest.mark.asyncio
async def test_admin_auth_accepts_valid_bearer_api_key():
    request = MagicMock()
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="super-secret-admin-token",
    )
    settings = SimpleNamespace(
        admin=SimpleNamespace(
            api_key_hash=AuthUtils.hash_admin_api_key("super-secret-admin-token"),
        )
    )

    with patch("services.auth.dependencies._admin_auth_session", new=AsyncMock(return_value=False)):
        with patch("services.auth.dependencies.get_settings", return_value=settings):
            await admin_auth(request=request, credentials=credentials)


@pytest.mark.asyncio
async def test_admin_auth_rejects_missing_session_and_invalid_api_key():
    request = MagicMock()
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="wrong-token",
    )
    settings = SimpleNamespace(
        admin=SimpleNamespace(
            api_key_hash=AuthUtils.hash_admin_api_key("expected-token"),
        )
    )

    with patch("services.auth.dependencies._admin_auth_session", new=AsyncMock(return_value=False)):
        with patch("services.auth.dependencies.get_settings", return_value=settings):
            with pytest.raises(HTTPException) as exc:
                await admin_auth(request=request, credentials=credentials)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid admin credentials"
