from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from services.auth.dependencies import relay_auth


@pytest.mark.asyncio
async def test_relay_auth_accepts_valid_bearer(monkeypatch):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="relay-secret")
    settings = SimpleNamespace(
        admin=SimpleNamespace(relay_token="relay-secret")
    )
    monkeypatch.setattr("services.auth.dependencies.get_settings", lambda: settings)

    await relay_auth(credentials=credentials)


@pytest.mark.asyncio
async def test_relay_auth_rejects_missing_header(monkeypatch):
    settings = SimpleNamespace(
        admin=SimpleNamespace(relay_token="expected")
    )
    monkeypatch.setattr("services.auth.dependencies.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc:
        await relay_auth(credentials=None)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_relay_auth_rejects_when_token_unset(monkeypatch):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="anything")
    settings = SimpleNamespace(admin=SimpleNamespace(relay_token=""))
    monkeypatch.setattr("services.auth.dependencies.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc:
        await relay_auth(credentials=credentials)

    assert exc.value.status_code == 401
    assert "not configured" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_relay_auth_rejects_wrong_token(monkeypatch):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
    settings = SimpleNamespace(
        admin=SimpleNamespace(relay_token="expected")
    )
    monkeypatch.setattr("services.auth.dependencies.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc:
        await relay_auth(credentials=credentials)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid relay token"


@pytest.mark.asyncio
async def test_relay_auth_rejects_non_bearer_scheme(monkeypatch):
    credentials = HTTPAuthorizationCredentials(scheme="Basic", credentials="blob")
    settings = SimpleNamespace(
        admin=SimpleNamespace(relay_token="expected")
    )
    monkeypatch.setattr("services.auth.dependencies.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc:
        await relay_auth(credentials=credentials)

    assert exc.value.status_code == 401
