from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from services.auth.dependencies import bot_auth
from services.auth.utils import AuthUtils


@pytest.mark.asyncio
async def test_bot_auth_accepts_valid_bearer_token(monkeypatch):
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="bot-secret-token",
    )
    settings = SimpleNamespace(
        bot_api=SimpleNamespace(
            api_key_hash=AuthUtils.hash_admin_api_key("bot-secret-token"),
        )
    )

    monkeypatch.setattr("services.auth.dependencies.get_settings", lambda: settings)

    await bot_auth(credentials=credentials)


@pytest.mark.asyncio
async def test_bot_auth_rejects_invalid_token(monkeypatch):
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="wrong-token",
    )
    settings = SimpleNamespace(
        bot_api=SimpleNamespace(
            api_key_hash=AuthUtils.hash_admin_api_key("expected-token"),
        )
    )

    monkeypatch.setattr("services.auth.dependencies.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc:
        await bot_auth(credentials=credentials)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid bot token"

