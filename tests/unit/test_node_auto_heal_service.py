from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.nodes.auto_heal_service import NodePlacementAutoHealService


def _node(
    *,
    node_id=None,
    role: str = "backend",
    is_active: bool = True,
    is_enabled: bool = True,
    is_draining: bool = False,
    region: str = "fi",
):
    node = MagicMock()
    node.id = node_id or uuid4()
    node.role = role
    node.is_active = is_active
    node.is_enabled = is_enabled
    node.is_draining = is_draining
    node.region = region
    return node


def _state(*, node_id, is_healthy: bool = True, last_seen_at: datetime | None = None):
    state = MagicMock()
    state.node_id = node_id
    state.is_healthy = is_healthy
    state.last_seen_at = last_seen_at or datetime.now(timezone.utc)
    return state


def _placement(*, desired_state: str = "active"):
    placement = MagicMock()
    placement.id = uuid4()
    placement.desired_state = desired_state
    return placement


@pytest.mark.asyncio
async def test_run_once_drains_and_migrates_stale_source(async_session):
    source = _node()
    target = _node()
    stale_state = _state(
        node_id=source.id,
        is_healthy=True,
        last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=240),
    )
    fresh_target_state = _state(node_id=target.id, is_healthy=True)

    service = NodePlacementAutoHealService(
        async_session,
        stale_after_sec=90,
        max_nodes=20,
        auto_undrain_enabled=False,
    )
    service.node_repository = AsyncMock()
    service.node_agent_state_repository = AsyncMock()
    service.placement_repository = AsyncMock()
    service.node_agent_transport = AsyncMock()
    service.routing_service = AsyncMock()

    service.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(source, stale_state), (target, fresh_target_state)]
    )
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(return_value={source.id: 2})
    service.node_repository.list_by_ids = AsyncMock(return_value=[source])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[stale_state])
    service.routing_service.select_nodes = AsyncMock(return_value=[target])
    service.placement_repository.list_active = AsyncMock(
        return_value=[_placement(desired_state="active"), _placement(desired_state="active")]
    )
    active_ids = [p.id for p in service.placement_repository.list_active.return_value if p.desired_state == "active"]
    service.placement_repository.bulk_migrate_backend = AsyncMock(return_value=(2, active_ids))

    out = await service.run_once()

    assert out.processed_nodes == 1
    assert out.drained_nodes == 1
    assert out.migrated_nodes == 1
    assert out.migrated_placements == 2
    assert out.skipped_nodes == 0
    assert out.orphan_active_placements == 2
    service.node_repository.update_by_id.assert_awaited_once_with(source.id, {"is_draining": True})


@pytest.mark.asyncio
async def test_run_once_skips_when_source_is_healthy(async_session):
    source = _node()
    source_state = _state(node_id=source.id, is_healthy=True)

    service = NodePlacementAutoHealService(
        async_session,
        stale_after_sec=90,
        max_nodes=20,
        auto_undrain_enabled=False,
    )
    service.node_repository = AsyncMock()
    service.node_agent_state_repository = AsyncMock()
    service.placement_repository = AsyncMock()
    service.node_agent_transport = AsyncMock()
    service.routing_service = AsyncMock()

    service.node_repository.list_active_with_agent_state = AsyncMock(return_value=[(source, source_state)])
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(return_value={source.id: 3})
    service.node_repository.list_by_ids = AsyncMock(return_value=[source])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[source_state])

    out = await service.run_once()

    assert out.processed_nodes == 0
    assert out.migrated_nodes == 0
    assert out.orphan_active_placements == 0
    service.node_repository.update_by_id.assert_not_awaited()
    service.placement_repository.bulk_migrate_backend.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_handles_missing_source_node_and_migrates(async_session):
    missing_source_id = uuid4()
    target = _node()
    target_state = _state(node_id=target.id, is_healthy=True)

    service = NodePlacementAutoHealService(
        async_session,
        stale_after_sec=90,
        max_nodes=20,
        auto_undrain_enabled=False,
    )
    service.node_repository = AsyncMock()
    service.node_agent_state_repository = AsyncMock()
    service.placement_repository = AsyncMock()
    service.node_agent_transport = AsyncMock()
    service.routing_service = AsyncMock()

    service.node_repository.list_active_with_agent_state = AsyncMock(return_value=[(target, target_state)])
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(return_value={missing_source_id: 1})
    service.node_repository.list_by_ids = AsyncMock(return_value=[])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[])
    service.routing_service.select_nodes = AsyncMock(return_value=[target])
    service.placement_repository.list_active = AsyncMock(return_value=[_placement(desired_state="active")])
    active_ids = [p.id for p in service.placement_repository.list_active.return_value if p.desired_state == "active"]
    service.placement_repository.bulk_migrate_backend = AsyncMock(return_value=(1, active_ids))

    out = await service.run_once()

    assert out.processed_nodes == 1
    assert out.drained_nodes == 0
    assert out.migrated_nodes == 1
    assert out.migrated_placements == 1


@pytest.mark.asyncio
async def test_run_once_auto_undrains_recovered_empty_node(async_session):
    recovering = _node(is_draining=True)
    recovering_state = _state(node_id=recovering.id, is_healthy=True)

    service = NodePlacementAutoHealService(
        async_session,
        stale_after_sec=90,
        max_nodes=20,
        auto_undrain_enabled=True,
    )
    service.node_repository = AsyncMock()
    service.node_agent_state_repository = AsyncMock()
    service.placement_repository = AsyncMock()
    service.routing_service = AsyncMock()

    rows = [(recovering, recovering_state)]
    service.node_repository.list_active_with_agent_state = AsyncMock(side_effect=[rows, rows])
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(return_value={})

    out = await service.run_once()

    assert out.undrained_nodes == 1
    service.node_repository.update_by_id.assert_awaited_once_with(
        recovering.id,
        {"is_draining": False},
    )


@pytest.mark.asyncio
async def test_run_once_auto_undrains_probe_drained_node_after_successful_probes(async_session):
    recovering = _node(is_draining=True)
    recovering_state = _state(node_id=recovering.id, is_healthy=True)
    recovering_state.details = {
        "heartbeat": {
            "drain_reason": "probe_auto_failure",
            "drained_at": datetime.now(timezone.utc).isoformat(),
        }
    }
    healthy_probe = SimpleNamespace(
        is_reachable=True,
        checked_at=datetime.now(timezone.utc),
    )

    service = NodePlacementAutoHealService(
        async_session,
        stale_after_sec=90,
        max_nodes=20,
        auto_undrain_enabled=True,
    )
    service.node_repository = AsyncMock()
    service.node_agent_state_repository = AsyncMock()
    service.placement_repository = AsyncMock()
    service.routing_service = AsyncMock()
    service.probe_repository = AsyncMock()
    service.probe_auto_undrain_enabled = True
    service.probe_auto_undrain_min_consecutive_successes = 2
    service.probe_auto_undrain_max_probe_age_sec = 600

    rows = [(recovering, recovering_state)]
    service.node_repository.list_active_with_agent_state = AsyncMock(side_effect=[rows, rows])
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(return_value={recovering.id: 2})
    service.probe_repository.get_latest_for_backend_node = AsyncMock(return_value=healthy_probe)
    service.probe_repository.list_recent_for_backend_node = AsyncMock(
        return_value=[healthy_probe, healthy_probe]
    )

    out = await service.run_once()

    assert out.undrained_nodes == 1
    service.node_repository.update_by_id.assert_awaited_once_with(
        recovering.id,
        {"is_draining": False},
    )
    service.node_agent_state_repository.update_by_node_id.assert_awaited_once()
