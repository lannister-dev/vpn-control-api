from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _patch_enqueue():
    with patch("services.nodes.auto_heal_service.enqueue_pool_snapshots_for_backend", new=AsyncMock()):
        yield

from services.nodes.auto_heal_service import NodePlacementAutoHealService


def _node(
    *,
    node_id=None,
    name: str = "node",
    role: str = "backend",
    is_active: bool = True,
    is_enabled: bool = True,
    is_draining: bool = False,
    region: str = "fi",
):
    node = MagicMock()
    node.id = node_id or uuid4()
    node.name = name
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


def _placement(*, key_id=None, desired_state: str = "active"):
    placement = MagicMock()
    placement.id = uuid4()
    placement.key_id = key_id or uuid4()
    placement.desired_state = desired_state
    return placement


def _make_service(async_session, *, stale_after_sec=90, auto_undrain_enabled=False):
    service = NodePlacementAutoHealService(
        async_session,
        stale_after_sec=stale_after_sec,
        max_nodes=20,
        auto_undrain_enabled=auto_undrain_enabled,
    )
    service.node_repository = AsyncMock()
    service.node_agent_state_repository = AsyncMock()
    service.placement_repository = AsyncMock()
    service.node_agent_transport = AsyncMock()
    service.routing_service = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_drains_stale_node_and_migrates_orphan_placements(async_session):
    source = _node(name="source-fi")
    target = _node(name="target-de")
    stale_state = _state(
        node_id=source.id,
        is_healthy=True,
        last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=240),
    )
    fresh_target_state = _state(node_id=target.id, is_healthy=True)
    p1 = _placement()
    p2 = _placement()

    service = _make_service(async_session)
    service.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(source, stale_state), (target, fresh_target_state)]
    )
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(
        return_value={source.id: 2}
    )
    service.node_repository.list_by_ids = AsyncMock(return_value=[source])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[stale_state])
    service.routing_service.select_nodes = AsyncMock(return_value=[target])
    service.placement_repository.list_active = AsyncMock(return_value=[p1, p2])
    # No other placements for these keys → orphans
    service.placement_repository.map_active_backend_nodes_by_key = AsyncMock(
        return_value={p1.key_id: {source.id}, p2.key_id: {source.id}}
    )
    service.placement_repository.bulk_migrate_backend = AsyncMock(
        return_value=(2, [p1.id, p2.id])
    )

    out = await service.run_once()

    assert out.processed_nodes == 1
    assert out.drained_nodes == 1
    assert out.migrated_nodes == 1
    assert out.migrated_placements == 2
    service.node_repository.update_by_id.assert_awaited_once_with(
        source.id, {"is_draining": True}
    )


@pytest.mark.asyncio
async def test_skips_covered_placements_migrates_only_orphans(async_session):
    """User has placements on source + target → covered, skip migration."""
    source = _node(name="source-lv")
    target = _node(name="target-fi")
    stale_state = _state(
        node_id=source.id,
        is_healthy=True,
        last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=240),
    )
    fresh_state = _state(node_id=target.id, is_healthy=True)

    covered_key = uuid4()
    orphan_key = uuid4()
    p_covered = _placement(key_id=covered_key)
    p_orphan = _placement(key_id=orphan_key)

    service = _make_service(async_session)
    service.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(source, stale_state), (target, fresh_state)]
    )
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(
        return_value={source.id: 2}
    )
    service.node_repository.list_by_ids = AsyncMock(return_value=[source])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[stale_state])
    service.routing_service.select_nodes = AsyncMock(return_value=[target])
    service.placement_repository.list_active = AsyncMock(return_value=[p_covered, p_orphan])
    # covered_key is on source AND target; orphan_key only on source
    service.placement_repository.map_active_backend_nodes_by_key = AsyncMock(
        return_value={
            covered_key: {source.id, target.id},
            orphan_key: {source.id},
        }
    )
    service.placement_repository.bulk_migrate_backend = AsyncMock(
        return_value=(1, [p_orphan.id])
    )

    out = await service.run_once()

    assert out.migrated_placements == 1
    # Only orphan was migrated
    call_args = service.placement_repository.bulk_migrate_backend.await_args
    assert call_args.kwargs["placement_ids"] == [p_orphan.id]
    assert call_args.kwargs["target_backend_id"] == target.id


@pytest.mark.asyncio
async def test_all_covered_no_migration(async_session):
    """All users have other healthy nodes → nothing to migrate."""
    source = _node(name="source-lv")
    target = _node(name="target-fi")
    stale_state = _state(
        node_id=source.id,
        is_healthy=True,
        last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=240),
    )
    fresh_state = _state(node_id=target.id, is_healthy=True)

    key1 = uuid4()
    key2 = uuid4()
    p1 = _placement(key_id=key1)
    p2 = _placement(key_id=key2)

    service = _make_service(async_session)
    service.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(source, stale_state), (target, fresh_state)]
    )
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(
        return_value={source.id: 2}
    )
    service.node_repository.list_by_ids = AsyncMock(return_value=[source])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[stale_state])
    service.routing_service.select_nodes = AsyncMock(return_value=[target])
    service.placement_repository.list_active = AsyncMock(return_value=[p1, p2])
    # Both keys exist on target too → covered
    service.placement_repository.map_active_backend_nodes_by_key = AsyncMock(
        return_value={
            key1: {source.id, target.id},
            key2: {source.id, target.id},
        }
    )

    out = await service.run_once()

    assert out.migrated_placements == 0
    assert out.skipped_nodes == 1
    service.placement_repository.bulk_migrate_backend.assert_not_awaited()


@pytest.mark.asyncio
async def test_orphans_distributed_evenly_across_targets(async_session):
    """4 orphan placements should spread across 2 targets (2 each)."""
    source = _node(name="source-lv")
    t1 = _node(name="target-fi")
    t2 = _node(name="target-de")
    stale_state = _state(
        node_id=source.id,
        is_healthy=True,
        last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=240),
    )

    orphans = [_placement() for _ in range(4)]

    service = _make_service(async_session)
    service.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(source, stale_state)]
    )
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(
        return_value={source.id: 4}
    )
    service.node_repository.list_by_ids = AsyncMock(return_value=[source])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[stale_state])
    service.routing_service.select_nodes = AsyncMock(return_value=[t1, t2])
    service.placement_repository.list_active = AsyncMock(return_value=orphans)
    service.placement_repository.map_active_backend_nodes_by_key = AsyncMock(
        return_value={p.key_id: {source.id} for p in orphans}
    )
    service.placement_repository.bulk_migrate_backend = AsyncMock(
        side_effect=lambda *, placement_ids, target_backend_id, **kw: (
            len(placement_ids), placement_ids
        )
    )

    out = await service.run_once()

    assert out.migrated_placements == 4
    calls = service.placement_repository.bulk_migrate_backend.await_args_list
    assert len(calls) == 2
    sizes = sorted(len(c.kwargs["placement_ids"]) for c in calls)
    assert sizes == [2, 2]


@pytest.mark.asyncio
async def test_skips_when_source_is_healthy(async_session):
    source = _node()
    source_state = _state(node_id=source.id, is_healthy=True)

    service = _make_service(async_session)
    service.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(source, source_state)]
    )
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(
        return_value={source.id: 3}
    )
    service.node_repository.list_by_ids = AsyncMock(return_value=[source])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[source_state])

    out = await service.run_once()

    assert out.processed_nodes == 0
    assert out.migrated_nodes == 0
    service.node_repository.update_by_id.assert_not_awaited()
    service.placement_repository.bulk_migrate_backend.assert_not_awaited()


@pytest.mark.asyncio
async def test_handles_missing_source_node_and_migrates(async_session):
    missing_source_id = uuid4()
    target = _node(name="target-fi")
    target_state = _state(node_id=target.id, is_healthy=True)
    p = _placement()

    service = _make_service(async_session)
    service.node_repository.list_active_with_agent_state = AsyncMock(
        return_value=[(target, target_state)]
    )
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(
        return_value={missing_source_id: 1}
    )
    service.node_repository.list_by_ids = AsyncMock(return_value=[])
    service.node_agent_state_repository.list_by_node_ids = AsyncMock(return_value=[])
    service.routing_service.select_nodes = AsyncMock(return_value=[target])
    service.placement_repository.list_active = AsyncMock(return_value=[p])
    service.placement_repository.map_active_backend_nodes_by_key = AsyncMock(
        return_value={p.key_id: {missing_source_id}}
    )
    service.placement_repository.bulk_migrate_backend = AsyncMock(return_value=(1, [p.id]))

    out = await service.run_once()

    assert out.processed_nodes == 1
    assert out.drained_nodes == 0
    assert out.migrated_nodes == 1
    assert out.migrated_placements == 1


@pytest.mark.asyncio
async def test_auto_undrains_recovered_empty_node(async_session):
    recovering = _node(is_draining=True)
    recovering_state = _state(node_id=recovering.id, is_healthy=True)

    service = _make_service(async_session, auto_undrain_enabled=True)
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
async def test_auto_undrains_probe_drained_node_after_successful_probes(async_session):
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

    service = _make_service(async_session, auto_undrain_enabled=True)
    service.probe_repository = AsyncMock()
    service.probe_auto_undrain_enabled = True
    service.probe_auto_undrain_min_consecutive_successes = 2
    service.probe_auto_undrain_max_probe_age_sec = 600

    rows = [(recovering, recovering_state)]
    service.node_repository.list_active_with_agent_state = AsyncMock(side_effect=[rows, rows])
    service.placement_repository.count_desired_active_by_backend_node = AsyncMock(
        return_value={recovering.id: 2}
    )
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
