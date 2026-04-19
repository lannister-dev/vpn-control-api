from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.entry.drain_service import EntryAutoDrainService
from services.nodes.constants import DRAIN_REASON_ENTRY_AUTO_DRAIN


def _entry(*, name="entry-1", is_draining=False, is_enabled=True, is_active=True):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        role="entry",
        is_enabled=is_enabled,
        is_draining=is_draining,
        is_active=is_active,
    )


def _agent_state(*, is_healthy=True, details=None, state_id=None):
    return SimpleNamespace(
        id=state_id or uuid4(),
        is_healthy=is_healthy,
        details=details or {},
    )


def _route(*, backend_id, entry_id, status="healthy", base_weight=50):
    return SimpleNamespace(
        id=uuid4(),
        node_id=backend_id,
        entry_node_id=entry_id,
        health_status=status,
        base_weight=base_weight,
        effective_weight=base_weight,
        is_active=True,
    )


def _assignment(*, entry_id, backend_id):
    return SimpleNamespace(
        id=uuid4(),
        entry_node_id=entry_id,
        backend_node_id=backend_id,
        is_active=True,
    )


def _service(async_session, *, probe_failure_threshold=3, healthy_ticks=3, auto_undrain=True):
    svc = EntryAutoDrainService(
        session=async_session,
        probe_failure_threshold=probe_failure_threshold,
        drain_reason="entry_auto_drain",
        max_nodes=10,
        auto_undrain_enabled=auto_undrain,
        healthy_ticks_for_recovery=healthy_ticks,
    )
    svc.node_repository = SimpleNamespace(update_by_id=AsyncMock())
    svc.agent_state_repository = SimpleNamespace(update_by_id=AsyncMock())
    svc.probe_repository = SimpleNamespace(count_consecutive_node_failures=AsyncMock(return_value=0))
    svc.route_repository = SimpleNamespace(update_by_id=AsyncMock())
    svc.assignment_repository = SimpleNamespace(list_by_entry=AsyncMock(return_value=[]))
    svc.session = SimpleNamespace(execute=AsyncMock())
    return svc


def _scalars(rows):
    return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


def _tuples(rows):
    return SimpleNamespace(tuples=lambda: SimpleNamespace(all=lambda: rows))


@pytest.mark.asyncio
async def test_unhealthy_agent_triggers_drain_and_block(async_session, monkeypatch):
    svc = _service(async_session)
    entry = _entry()
    backend_id = uuid4()
    agent_state = _agent_state(is_healthy=False, details={})

    route = _route(backend_id=backend_id, entry_id=entry.id, status="healthy")
    svc.session.execute = AsyncMock(side_effect=[
        _tuples([(entry, agent_state)]),
        _scalars([route]),
    ])
    svc.assignment_repository.list_by_entry = AsyncMock(return_value=[_assignment(entry_id=entry.id, backend_id=backend_id)])
    snapshot_count = AsyncMock(return_value=2)
    monkeypatch.setattr(
        "services.entry.drain_service.enqueue_pool_snapshots_for_backend",
        snapshot_count,
    )

    result = await svc.run()

    assert result.drained == 1
    assert result.routes_blocked == 1
    assert result.snapshots_enqueued == 2
    assert entry.is_draining is True
    svc.node_repository.update_by_id.assert_awaited_once()
    svc.route_repository.update_by_id.assert_awaited_once()
    assert svc.route_repository.update_by_id.await_args.args[0] == route.id
    assert svc.route_repository.update_by_id.await_args.args[1]["health_status"] == "blocked"
    svc.agent_state_repository.update_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_failures_trigger_drain(async_session, monkeypatch):
    svc = _service(async_session, probe_failure_threshold=3)
    entry = _entry()
    agent_state = _agent_state(is_healthy=True)
    svc.session.execute = AsyncMock(side_effect=[
        _tuples([(entry, agent_state)]),
        _scalars([]),
    ])
    svc.probe_repository.count_consecutive_node_failures = AsyncMock(return_value=5)
    monkeypatch.setattr(
        "services.entry.drain_service.enqueue_pool_snapshots_for_backend",
        AsyncMock(return_value=0),
    )

    result = await svc.run()

    assert result.drained == 1
    assert entry.is_draining is True


@pytest.mark.asyncio
async def test_healthy_entry_skipped(async_session, monkeypatch):
    svc = _service(async_session)
    entry = _entry()
    agent_state = _agent_state(is_healthy=True)
    svc.session.execute = AsyncMock(return_value=_tuples([(entry, agent_state)]))
    svc.probe_repository.count_consecutive_node_failures = AsyncMock(return_value=0)

    result = await svc.run()

    assert result.drained == 0
    assert result.skipped == 1
    svc.node_repository.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_undrain_after_healthy_ticks(async_session, monkeypatch):
    svc = _service(async_session, healthy_ticks=3)
    entry = _entry(is_draining=True)
    agent_state = _agent_state(
        is_healthy=True,
        details={
            "heartbeat": {
                "drain_reason": DRAIN_REASON_ENTRY_AUTO_DRAIN,
                "consecutive_healthy": 4,
            },
        },
    )
    blocked_route = _route(backend_id=uuid4(), entry_id=entry.id, status="blocked")
    svc.session.execute = AsyncMock(side_effect=[
        _tuples([(entry, agent_state)]),
        _scalars([blocked_route]),
    ])
    svc.probe_repository.count_consecutive_node_failures = AsyncMock(return_value=0)
    svc.assignment_repository.list_by_entry = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "services.entry.drain_service.enqueue_pool_snapshots_for_backend",
        AsyncMock(return_value=0),
    )

    result = await svc.run()

    assert result.undrained == 1
    assert result.routes_unblocked == 1
    assert entry.is_draining is False
    assert svc.route_repository.update_by_id.await_args.args[1]["health_status"] == "warming_up"


@pytest.mark.asyncio
async def test_auto_undrain_skipped_when_not_our_drain(async_session, monkeypatch):
    svc = _service(async_session, healthy_ticks=3)
    entry = _entry(is_draining=True)
    agent_state = _agent_state(
        is_healthy=True,
        details={"heartbeat": {"drain_reason": "unhealthy_heartbeat", "consecutive_healthy": 10}},
    )
    svc.session.execute = AsyncMock(return_value=_tuples([(entry, agent_state)]))
    svc.probe_repository.count_consecutive_node_failures = AsyncMock(return_value=0)

    result = await svc.run()

    assert result.undrained == 0
    assert result.skipped == 1
    assert entry.is_draining is True


@pytest.mark.asyncio
async def test_auto_undrain_waits_for_enough_healthy_ticks(async_session, monkeypatch):
    svc = _service(async_session, healthy_ticks=5)
    entry = _entry(is_draining=True)
    agent_state = _agent_state(
        is_healthy=True,
        details={"heartbeat": {"drain_reason": DRAIN_REASON_ENTRY_AUTO_DRAIN, "consecutive_healthy": 2}},
    )
    svc.session.execute = AsyncMock(return_value=_tuples([(entry, agent_state)]))
    svc.probe_repository.count_consecutive_node_failures = AsyncMock(return_value=0)

    result = await svc.run()

    assert result.undrained == 0
    assert entry.is_draining is True
