from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _patch_enqueue():
    with patch("services.nodes.service.enqueue_pool_snapshots_for_backend", new=AsyncMock()):
        yield

from services.nodes.schemas import (
    HeartbeatDetails,
    HeartbeatRuntime,
    HeartbeatStats,
    NodeHeartbeatIn,
)
from services.nodes.service import VpnNodeService


def _inject_policy(service, *, unhealthy_drain_threshold: int, healthy_undrain_threshold: int) -> None:
    service._policy_cache = SimpleNamespace(
        heartbeat_unhealthy_drain_threshold=unhealthy_drain_threshold,
        heartbeat_healthy_undrain_threshold=healthy_undrain_threshold,
        entry_apply_fail_threshold=3,
        entry_apply_fail_unhealthy=True,
    )


def _payload(*, is_healthy: bool, runtime_ready: bool | None = None) -> NodeHeartbeatIn:
    runtime_ready = is_healthy if runtime_ready is None else runtime_ready
    return NodeHeartbeatIn(
        agent_version="1.3",
        is_healthy=is_healthy,
        details=HeartbeatDetails(
            runtime=HeartbeatRuntime(
                ready=runtime_ready,
                last_error=None if runtime_ready else "runtime_error",
            ),
            stats=HeartbeatStats(
                poll_count=10,
                applied=0,
                failed=0 if runtime_ready else 1,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_handle_heartbeat_does_not_drain_below_unhealthy_threshold(async_session):
    service = VpnNodeService(async_session)
    _inject_policy(service, unhealthy_drain_threshold=2, healthy_undrain_threshold=3)
    service.node_agent_state_repository = AsyncMock()
    service.vpn_node_repository = AsyncMock()
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(
            details={
                "heartbeat": {
                    "consecutive_unhealthy": 0,
                    "consecutive_healthy": 5,
                }
            }
        )
    )
    node = SimpleNamespace(
        id=uuid4(),
        is_draining=False, drain_source=None,
        is_active=True,
        is_enabled=True,
    )

    await service.handle_heartbeat(node=node, payload=_payload(is_healthy=False))

    service.vpn_node_repository.update_by_id.assert_not_awaited()
    upsert_payload = service.node_agent_state_repository.upsert.await_args.args[0]
    assert upsert_payload["details"]["heartbeat"]["consecutive_unhealthy"] == 1
    assert upsert_payload["details"]["heartbeat"]["consecutive_healthy"] == 0
    assert "drain_reason" not in upsert_payload["details"]["heartbeat"]


@pytest.mark.asyncio
async def test_handle_heartbeat_drains_on_unhealthy_threshold(async_session):
    service = VpnNodeService(async_session)
    _inject_policy(service, unhealthy_drain_threshold=2, healthy_undrain_threshold=3)
    service.node_agent_state_repository = AsyncMock()
    service.vpn_node_repository = AsyncMock()
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(
            details={
                "heartbeat": {
                    "consecutive_unhealthy": 1,
                    "consecutive_healthy": 0,
                }
            }
        )
    )
    node = SimpleNamespace(
        id=uuid4(),
        is_draining=False, drain_source=None,
        is_active=True,
        is_enabled=True,
        role="backend",
    )

    await service.handle_heartbeat(node=node, payload=_payload(is_healthy=False))

    service.vpn_node_repository.update_by_id.assert_awaited_once_with(
        node.id,
        {"is_draining": True, "drain_source": "auto_heal"},
    )
    upsert_payload = service.node_agent_state_repository.upsert.await_args.args[0]
    assert upsert_payload["details"]["heartbeat"]["consecutive_unhealthy"] == 2
    assert upsert_payload["details"]["heartbeat"]["consecutive_healthy"] == 0
    assert upsert_payload["details"]["heartbeat"]["drain_reason"] == "unhealthy_heartbeat"


@pytest.mark.asyncio
async def test_handle_heartbeat_undrains_when_recovered_after_threshold(async_session):
    service = VpnNodeService(async_session)
    _inject_policy(service, unhealthy_drain_threshold=2, healthy_undrain_threshold=3)
    service.node_agent_state_repository = AsyncMock()
    service.vpn_node_repository = AsyncMock()
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(
            details={
                "heartbeat": {
                    "consecutive_unhealthy": 0,
                    "consecutive_healthy": 2,
                    "drain_reason": "unhealthy_heartbeat",
                }
            }
        )
    )
    node = SimpleNamespace(
        id=uuid4(),
        is_draining=True, drain_source=None,
        is_active=True,
        is_enabled=True,
        role="backend",
    )

    await service.handle_heartbeat(node=node, payload=_payload(is_healthy=True))

    service.vpn_node_repository.update_by_id.assert_awaited_once_with(
        node.id,
        {"is_draining": False, "drain_source": None},
    )
    upsert_payload = service.node_agent_state_repository.upsert.await_args.args[0]
    assert upsert_payload["details"]["heartbeat"]["consecutive_unhealthy"] == 0
    assert upsert_payload["details"]["heartbeat"]["consecutive_healthy"] == 3
    assert "drain_reason" not in upsert_payload["details"]["heartbeat"]


@pytest.mark.asyncio
async def test_handle_heartbeat_does_not_undrain_for_non_heartbeat_reason(async_session):
    service = VpnNodeService(async_session)
    _inject_policy(service, unhealthy_drain_threshold=2, healthy_undrain_threshold=3)
    service.node_agent_state_repository = AsyncMock()
    service.vpn_node_repository = AsyncMock()
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(
            details={
                "heartbeat": {
                    "consecutive_unhealthy": 0,
                    "consecutive_healthy": 10,
                    "drain_reason": "manual_admin",
                }
            }
        )
    )
    node = SimpleNamespace(
        id=uuid4(),
        is_draining=True, drain_source=None,
        is_active=True,
        is_enabled=True,
    )

    await service.handle_heartbeat(node=node, payload=_payload(is_healthy=True))

    service.vpn_node_repository.update_by_id.assert_not_awaited()
    upsert_payload = service.node_agent_state_repository.upsert.await_args.args[0]
    assert upsert_payload["details"]["heartbeat"]["consecutive_unhealthy"] == 0
    assert upsert_payload["details"]["heartbeat"]["consecutive_healthy"] == 11
    assert upsert_payload["details"]["heartbeat"]["drain_reason"] == "manual_admin"


@pytest.mark.asyncio
async def test_handle_heartbeat_treats_runtime_not_ready_as_unhealthy(async_session):
    service = VpnNodeService(async_session)
    _inject_policy(service, unhealthy_drain_threshold=1, healthy_undrain_threshold=3)
    service.node_agent_state_repository = AsyncMock()
    service.vpn_node_repository = AsyncMock()
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(details={})
    )
    node = SimpleNamespace(
        id=uuid4(),
        is_draining=False, drain_source=None,
        is_active=True,
        is_enabled=True,
        role="backend",
    )

    await service.handle_heartbeat(
        node=node,
        payload=_payload(is_healthy=True, runtime_ready=False),
    )

    service.vpn_node_repository.update_by_id.assert_awaited_once_with(
        node.id,
        {"is_draining": True, "drain_source": "auto_heal"},
    )
    upsert_payload = service.node_agent_state_repository.upsert.await_args.args[0]
    assert upsert_payload["is_healthy"] is False
    assert upsert_payload["details"]["runtime"]["ready"] is False
    assert upsert_payload["details"]["heartbeat"]["consecutive_unhealthy"] == 1


@pytest.mark.asyncio
async def test_handle_heartbeat_does_not_undrain_when_runtime_not_ready(async_session):
    service = VpnNodeService(async_session)
    _inject_policy(service, unhealthy_drain_threshold=2, healthy_undrain_threshold=3)
    service.node_agent_state_repository = AsyncMock()
    service.vpn_node_repository = AsyncMock()
    service.node_agent_state_repository.get_one_by = AsyncMock(
        return_value=SimpleNamespace(
            details={
                "heartbeat": {
                    "consecutive_unhealthy": 0,
                    "consecutive_healthy": 2,
                    "drain_reason": "unhealthy_heartbeat",
                }
            }
        )
    )
    node = SimpleNamespace(
        id=uuid4(),
        is_draining=True, drain_source=None,
        is_active=True,
        is_enabled=True,
    )

    await service.handle_heartbeat(
        node=node,
        payload=_payload(is_healthy=True, runtime_ready=False),
    )

    service.vpn_node_repository.update_by_id.assert_not_awaited()
    upsert_payload = service.node_agent_state_repository.upsert.await_args.args[0]
    assert upsert_payload["is_healthy"] is False
    assert upsert_payload["details"]["heartbeat"]["consecutive_unhealthy"] == 1
    assert upsert_payload["details"]["heartbeat"]["consecutive_healthy"] == 0
    assert upsert_payload["details"]["heartbeat"]["drain_reason"] == "unhealthy_heartbeat"
