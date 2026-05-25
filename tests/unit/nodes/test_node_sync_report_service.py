from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.nodes.schemas import NodeSyncReportIn
from services.nodes.service import VpnNodeService


@pytest.mark.asyncio
async def test_handle_sync_report_updates_existing_state(async_session):
    service = VpnNodeService(async_session)
    service.node_agent_state_repository = AsyncMock()
    service.node_agent_identity_repository = AsyncMock()
    service.sync_report_debounce_sec = 10
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(
            details={"runtime": {"ready": True}},
            last_sync_at=datetime.now(timezone.utc) - timedelta(seconds=20),
            last_config_version=10,
        )
    )

    node = SimpleNamespace(id=uuid4())
    payload = NodeSyncReportIn(synced_count=5, config_version=11)

    await service.handle_sync_report(node=node, payload=payload)

    service.node_agent_state_repository.update_by_node_id.assert_awaited_once()
    kwargs = service.node_agent_state_repository.update_by_node_id.await_args.kwargs
    assert kwargs["node_id"] == node.id
    assert kwargs["data"]["last_config_version"] == 11
    assert kwargs["data"]["details"]["runtime"] == {"ready": True}
    assert kwargs["data"]["details"]["sync"]["synced_count"] == 5
    service.node_agent_identity_repository.clear_full_resync_required_for_node.assert_awaited_once_with(
        node_id=node.id,
    )
    assert isinstance(kwargs["data"]["details"]["sync"]["reported_at"], str)
    datetime.fromisoformat(kwargs["data"]["details"]["sync"]["reported_at"])


@pytest.mark.asyncio
async def test_handle_sync_report_creates_state_when_missing(async_session):
    service = VpnNodeService(async_session)
    service.node_agent_state_repository = AsyncMock()
    service.node_agent_identity_repository = AsyncMock()
    service.sync_report_debounce_sec = 10
    service.node_agent_state_repository.get_one_by = AsyncMock(return_value=None)

    node = SimpleNamespace(id=uuid4())
    payload = NodeSyncReportIn(synced_count=2, config_version=None)

    await service.handle_sync_report(node=node, payload=payload)

    service.node_agent_state_repository.upsert.assert_awaited_once()
    upsert_payload = service.node_agent_state_repository.upsert.await_args.args[0]
    assert upsert_payload["node_id"] == node.id
    assert upsert_payload["details"]["sync"]["synced_count"] == 2
    service.node_agent_identity_repository.clear_full_resync_required_for_node.assert_awaited_once_with(
        node_id=node.id,
    )
    assert isinstance(upsert_payload["details"]["sync"]["reported_at"], str)
    datetime.fromisoformat(upsert_payload["details"]["sync"]["reported_at"])
    assert "last_config_version" not in upsert_payload


@pytest.mark.asyncio
async def test_handle_sync_report_debounces_identical_payload(async_session):
    service = VpnNodeService(async_session)
    service.sync_report_debounce_sec = 30
    service.node_agent_state_repository = AsyncMock()
    service.node_agent_identity_repository = AsyncMock()
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(
            details={
                "sync": {
                    "synced_count": 5,
                    "reported_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            last_sync_at=datetime.now(timezone.utc) - timedelta(seconds=3),
            last_config_version=11,
        )
    )

    node = SimpleNamespace(id=uuid4())
    payload = NodeSyncReportIn(synced_count=5, config_version=11)

    updated = await service.handle_sync_report(node=node, payload=payload)

    assert updated is False
    service.node_agent_state_repository.update_by_node_id.assert_not_awaited()
    service.node_agent_state_repository.upsert.assert_not_awaited()
    service.node_agent_identity_repository.clear_full_resync_required_for_node.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_sync_report_persists_inventory_metadata(async_session):
    service = VpnNodeService(async_session)
    service.node_agent_state_repository = AsyncMock()
    service.node_agent_identity_repository = AsyncMock()
    service.sync_report_debounce_sec = 10
    service.node_agent_state_repository.get_one_by = AsyncMock(return_value=None)

    node = SimpleNamespace(id=uuid4())
    payload = NodeSyncReportIn(
        synced_count=7,
        config_version=9,
        inventory_hash="sha256:test",
        inventory_count=7,
        full_resync_completed=True,
    )

    await service.handle_sync_report(node=node, payload=payload)

    upsert_payload = service.node_agent_state_repository.upsert.await_args.args[0]
    assert upsert_payload["details"]["sync"]["inventory_hash"] == "sha256:test"
    assert upsert_payload["details"]["sync"]["inventory_count"] == 7
    assert upsert_payload["details"]["sync"]["full_resync_completed"] is True


@pytest.mark.asyncio
async def test_handle_sync_report_does_not_debounce_inventory_change(async_session):
    service = VpnNodeService(async_session)
    service.sync_report_debounce_sec = 30
    service.node_agent_state_repository = AsyncMock()
    service.node_agent_identity_repository = AsyncMock()
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(
            details={
                "sync": {
                    "synced_count": 5,
                    "inventory_hash": "sha256:old",
                    "inventory_count": 5,
                    "reported_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            last_sync_at=datetime.now(timezone.utc) - timedelta(seconds=3),
            last_config_version=11,
        )
    )

    node = SimpleNamespace(id=uuid4())
    payload = NodeSyncReportIn(
        synced_count=5,
        config_version=11,
        inventory_hash="sha256:new",
        inventory_count=5,
    )

    updated = await service.handle_sync_report(node=node, payload=payload)

    assert updated is True
    service.node_agent_state_repository.update_by_node_id.assert_awaited_once()
