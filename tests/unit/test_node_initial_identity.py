from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.nodes.service import NodeBootstrapConflictError, VpnNodeService


@pytest.mark.asyncio
async def test_initial_with_agent_instance_issues_identity_token_without_node_rotation(async_session):
    service = VpnNodeService(async_session)
    node_id = uuid4()
    agent_instance_id = uuid4()
    existing_node = SimpleNamespace(id=node_id, auth_token_hash="old-node-hash")
    service.vpn_node_repository = SimpleNamespace(
        get_by_node_key=AsyncMock(return_value=existing_node),
        list_by_internal_ip=AsyncMock(return_value=[]),
        update_by_id=AsyncMock(),
        create=AsyncMock(),
    )
    service.node_agent_identity_repository = SimpleNamespace(
        upsert_token=AsyncMock(),
    )

    out = await service.initial(
        source_ip="10.0.1.180",
        node_key="node-180",
        agent_instance_id=agent_instance_id,
    )

    assert out.node_id == str(node_id)
    assert out.agent_instance_id == str(agent_instance_id)
    assert out.node_auth_token
    service.vpn_node_repository.update_by_id.assert_not_awaited()
    service.vpn_node_repository.create.assert_not_awaited()
    service.node_agent_identity_repository.upsert_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_strict_mode_creates_node_by_node_key(async_session):
    service = VpnNodeService(async_session)
    created_node = SimpleNamespace(id=uuid4())
    agent_instance_id = uuid4()
    service.vpn_node_repository = SimpleNamespace(
        get_by_node_key=AsyncMock(return_value=None),
        list_by_internal_ip=AsyncMock(return_value=[]),
        update_by_id=AsyncMock(),
        create=AsyncMock(return_value=created_node),
    )
    service.node_agent_identity_repository = SimpleNamespace(
        upsert_token=AsyncMock(),
    )

    out = await service.initial(
        source_ip="10.0.1.180",
        node_key="node-180",
        agent_instance_id=agent_instance_id,
    )

    assert out.node_id == str(created_node.id)
    assert out.agent_instance_id == str(agent_instance_id)
    assert out.node_auth_token
    service.vpn_node_repository.create.assert_awaited_once()
    service.vpn_node_repository.update_by_id.assert_not_awaited()
    service.node_agent_identity_repository.upsert_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_with_node_key_does_not_merge_into_different_key_node(async_session):
    service = VpnNodeService(async_session)
    created_node = SimpleNamespace(id=uuid4())
    service.vpn_node_repository = SimpleNamespace(
        get_by_node_key=AsyncMock(return_value=None),
        list_by_internal_ip=AsyncMock(return_value=[]),
        update_by_id=AsyncMock(),
        create=AsyncMock(return_value=created_node),
    )
    service.node_agent_identity_repository = SimpleNamespace(
        upsert_token=AsyncMock(),
    )

    out = await service.initial(
        source_ip="10.0.1.180",
        node_key="node-b",
        agent_instance_id=uuid4(),
    )

    assert out.node_id == str(created_node.id)
    service.vpn_node_repository.create.assert_awaited_once()
    create_payload = service.vpn_node_repository.create.await_args.args[0]
    assert create_payload["node_key"] == "node-b"
    assert create_payload["name"].startswith("node-10-0-1-180-node-b")
    service.vpn_node_repository.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_initial_recovers_existing_node_by_source_ip(async_session):
    service = VpnNodeService(async_session)
    existing_node = SimpleNamespace(id=uuid4(), auth_token_hash="old-node-hash")
    service.vpn_node_repository = SimpleNamespace(
        get_by_node_key=AsyncMock(return_value=None),
        list_by_internal_ip=AsyncMock(return_value=[existing_node]),
        update_by_id=AsyncMock(),
        create=AsyncMock(),
    )
    service.node_agent_identity_repository = SimpleNamespace(
        upsert_token=AsyncMock(),
    )

    out = await service.initial(
        source_ip="10.0.1.180",
        node_key="new-node-key",
        agent_instance_id=uuid4(),
    )

    assert out.node_id == str(existing_node.id)
    service.vpn_node_repository.update_by_id.assert_awaited_once_with(
        existing_node.id,
        {"node_key": "new-node-key"},
    )
    service.vpn_node_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_initial_recovery_ambiguous_source_ip_raises_conflict(async_session):
    service = VpnNodeService(async_session)
    service.vpn_node_repository = SimpleNamespace(
        get_by_node_key=AsyncMock(return_value=None),
        list_by_internal_ip=AsyncMock(return_value=[SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]),
        update_by_id=AsyncMock(),
        create=AsyncMock(),
    )
    service.node_agent_identity_repository = SimpleNamespace(
        upsert_token=AsyncMock(),
    )

    with pytest.raises(NodeBootstrapConflictError):
        await service.initial(
            source_ip="10.0.1.180",
            node_key="new-node-key",
            agent_instance_id=uuid4(),
        )

    service.vpn_node_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_initial_with_create_disabled_raises_conflict(async_session):
    service = VpnNodeService(async_session)
    service.bootstrap_allow_create = False
    service.vpn_node_repository = SimpleNamespace(
        get_by_node_key=AsyncMock(return_value=None),
        list_by_internal_ip=AsyncMock(return_value=[]),
        update_by_id=AsyncMock(),
        create=AsyncMock(),
    )
    service.node_agent_identity_repository = SimpleNamespace(
        upsert_token=AsyncMock(),
    )

    with pytest.raises(NodeBootstrapConflictError):
        await service.initial(
            source_ip="10.0.1.180",
            node_key="new-node-key",
            agent_instance_id=uuid4(),
        )

    service.vpn_node_repository.create.assert_not_awaited()
