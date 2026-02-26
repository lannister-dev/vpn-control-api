from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from services.auth.dependencies import node_auth
from services.auth.utils import AuthUtils


@pytest.mark.asyncio
async def test_node_auth_identity_token_success():
    node_id = uuid4()
    agent_instance_id = uuid4()
    raw_token = "agent-token"
    node = SimpleNamespace(
        id=node_id,
        auth_token_hash="unused-for-identity",
    )
    identity = SimpleNamespace(
        auth_token_hash=AuthUtils.hash_node_token(raw_token),
    )
    service = SimpleNamespace(
        vpn_node_repository=SimpleNamespace(get_by_id=AsyncMock(return_value=node)),
        node_agent_identity_repository=SimpleNamespace(
            get_by_node_and_instance=AsyncMock(return_value=identity),
            get_by_instance_and_token_hash=AsyncMock(),
        ),
    )

    authed_node = await node_auth(
        x_node_id=str(node_id),
        x_agent_instance_id=agent_instance_id,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_token),
        service=service,
    )

    assert authed_node is node
    service.node_agent_identity_repository.get_by_node_and_instance.assert_awaited_once_with(
        node_id=node_id,
        agent_instance_id=agent_instance_id,
    )


@pytest.mark.asyncio
async def test_node_auth_identity_token_invalid_raises_401():
    node_id = uuid4()
    agent_instance_id = uuid4()
    node = SimpleNamespace(
        id=node_id,
        auth_token_hash="unused-for-identity",
    )
    identity = SimpleNamespace(auth_token_hash=AuthUtils.hash_node_token("right-token"))
    service = SimpleNamespace(
        vpn_node_repository=SimpleNamespace(get_by_id=AsyncMock(return_value=node)),
        node_agent_identity_repository=SimpleNamespace(
            get_by_node_and_instance=AsyncMock(return_value=identity),
            get_by_instance_and_token_hash=AsyncMock(return_value=None),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await node_auth(
            x_node_id=str(node_id),
            x_agent_instance_id=agent_instance_id,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-token"),
            service=service,
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_node_auth_missing_agent_instance_id_raises_401():
    node_id = uuid4()
    node = SimpleNamespace(
        id=node_id,
        auth_token_hash=AuthUtils.hash_node_token("unused"),
    )
    service = SimpleNamespace(
        vpn_node_repository=SimpleNamespace(get_by_id=AsyncMock(return_value=node)),
        node_agent_identity_repository=SimpleNamespace(
            get_by_node_and_instance=AsyncMock(),
            get_by_instance_and_token_hash=AsyncMock(),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await node_auth(
            x_node_id=str(node_id),
            x_agent_instance_id=None,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            service=service,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "X-Agent-Instance-ID header required"


@pytest.mark.asyncio
async def test_node_auth_without_node_id_uses_agent_identity_token():
    node_id = uuid4()
    agent_instance_id = uuid4()
    raw_token = "agent-token"
    node = SimpleNamespace(
        id=node_id,
        auth_token_hash="unused-for-identity",
    )
    identity = SimpleNamespace(
        node_id=node_id,
        auth_token_hash=AuthUtils.hash_node_token(raw_token),
    )
    service = SimpleNamespace(
        vpn_node_repository=SimpleNamespace(get_by_id=AsyncMock(return_value=node)),
        node_agent_identity_repository=SimpleNamespace(
            get_by_node_and_instance=AsyncMock(),
            get_by_instance_and_token_hash=AsyncMock(return_value=identity),
        ),
    )

    authed_node = await node_auth(
        x_node_id=None,
        x_agent_instance_id=agent_instance_id,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_token),
        service=service,
    )

    assert authed_node is node
    service.node_agent_identity_repository.get_by_node_and_instance.assert_not_awaited()
    service.node_agent_identity_repository.get_by_instance_and_token_hash.assert_awaited_once_with(
        agent_instance_id=agent_instance_id,
        token_hash=AuthUtils.hash_node_token(raw_token),
    )
