from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.nodes.service import VpnNodeService


@pytest.mark.asyncio
async def test_initial_with_agent_instance_issues_identity_token_without_node_rotation(async_session):
    service = VpnNodeService(async_session)
    node_id = uuid4()
    agent_instance_id = uuid4()
    existing_node = SimpleNamespace(id=node_id, auth_token_hash="old-node-hash")
    service.vpn_node_repository = SimpleNamespace(
        get_by_internal_ip=AsyncMock(return_value=existing_node),
        update_by_id=AsyncMock(),
        create=AsyncMock(),
    )
    service.node_agent_identity_repository = SimpleNamespace(
        upsert_token=AsyncMock(),
    )

    out = await service.initial(
        source_ip="10.0.1.180",
        agent_instance_id=agent_instance_id,
    )

    assert out.node_id == str(node_id)
    assert out.agent_instance_id == str(agent_instance_id)
    assert out.node_auth_token
    service.vpn_node_repository.update_by_id.assert_not_awaited()
    service.vpn_node_repository.create.assert_not_awaited()
    service.node_agent_identity_repository.upsert_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_legacy_mode_rotates_node_token(async_session):
    service = VpnNodeService(async_session)
    node_id = uuid4()
    existing_node = SimpleNamespace(id=node_id, auth_token_hash="old-node-hash")
    service.vpn_node_repository = SimpleNamespace(
        get_by_internal_ip=AsyncMock(return_value=existing_node),
        update_by_id=AsyncMock(),
        create=AsyncMock(),
    )
    service.node_agent_identity_repository = SimpleNamespace(
        upsert_token=AsyncMock(),
    )

    out = await service.initial(
        source_ip="10.0.1.180",
        agent_instance_id=None,
    )

    assert out.node_id == str(node_id)
    assert out.agent_instance_id is None
    assert out.node_auth_token
    service.vpn_node_repository.update_by_id.assert_awaited_once()
    service.node_agent_identity_repository.upsert_token.assert_not_awaited()
