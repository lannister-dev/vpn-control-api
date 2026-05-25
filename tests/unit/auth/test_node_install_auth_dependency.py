from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from services.auth.dependencies import NodeInstallCredentials, node_install_auth
from services.auth.utils import AuthUtils


def _pending_node(*, raw_token: str, is_active: bool = True, bootstrapped_at=None,
                  expires_at: datetime | None = None):
    return SimpleNamespace(
        id=uuid4(),
        name="vpn-yc-entry-42",
        role="entry",
        region="ru-central1-d",
        is_active=is_active,
        auth_token_hash=AuthUtils.hash_node_token(raw_token),
        bootstrapped_at=bootstrapped_at,
        bootstrap_token_expires_at=expires_at,
    )


def _service_for(node):
    return SimpleNamespace(
        vpn_node_repository=SimpleNamespace(
            get_by_auth_token_hash=AsyncMock(return_value=node),
        ),
    )


@pytest.mark.asyncio
async def test_node_install_auth_accepts_bearer_token():
    raw = "bootstrap-one-shot"
    node = _pending_node(
        raw_token=raw,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    service = _service_for(node)

    creds = await node_install_auth(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw),
        token=None,
        service=service,
    )

    assert isinstance(creds, NodeInstallCredentials)
    assert creds.node is node
    assert creds.raw_token == raw


@pytest.mark.asyncio
async def test_node_install_auth_accepts_token_query_param():
    raw = "bootstrap-one-shot"
    node = _pending_node(
        raw_token=raw,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    service = _service_for(node)

    creds = await node_install_auth(
        credentials=None,
        token=raw,
        service=service,
    )

    assert creds.raw_token == raw


@pytest.mark.asyncio
async def test_node_install_auth_rejects_missing_token():
    service = SimpleNamespace(
        vpn_node_repository=SimpleNamespace(get_by_auth_token_hash=AsyncMock()),
    )

    with pytest.raises(HTTPException) as exc:
        await node_install_auth(credentials=None, token=None, service=service)

    assert exc.value.status_code == 401
    service.vpn_node_repository.get_by_auth_token_hash.assert_not_awaited()


@pytest.mark.asyncio
async def test_node_install_auth_rejects_unknown_token():
    service = SimpleNamespace(
        vpn_node_repository=SimpleNamespace(
            get_by_auth_token_hash=AsyncMock(return_value=None),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await node_install_auth(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="nope"),
            token=None,
            service=service,
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_node_install_auth_rejects_inactive_node():
    raw = "bootstrap-one-shot"
    node = _pending_node(
        raw_token=raw,
        is_active=False,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    service = _service_for(node)

    with pytest.raises(HTTPException) as exc:
        await node_install_auth(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw),
            token=None,
            service=service,
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_node_install_auth_rejects_already_bootstrapped_node():
    raw = "bootstrap-one-shot"
    node = _pending_node(
        raw_token=raw,
        bootstrapped_at=datetime.now(timezone.utc) - timedelta(days=1),
        expires_at=None,
    )
    service = _service_for(node)

    with pytest.raises(HTTPException) as exc:
        await node_install_auth(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw),
            token=None,
            service=service,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_node_install_auth_rejects_expired_token():
    raw = "bootstrap-one-shot"
    node = _pending_node(
        raw_token=raw,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    service = _service_for(node)

    with pytest.raises(HTTPException) as exc:
        await node_install_auth(
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw),
            token=None,
            service=service,
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_node_install_auth_tolerates_naive_expiry_in_db():
    """Legacy rows may store naive UTC datetimes; dep must treat them as UTC."""
    raw = "bootstrap-one-shot"
    node = _pending_node(
        raw_token=raw,
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None),
    )
    service = _service_for(node)

    creds = await node_install_auth(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw),
        token=None,
        service=service,
    )

    assert creds.raw_token == raw
