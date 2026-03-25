import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.config import NatsConfig
from services.nodes.agent.runtime import NodeAgentRuntime
from services.nodes.agent.schemas import (
    HeartbeatEvent,
    PlacementApplyResultEvent,
    SyncReportEvent,
    TransportAppliedState,
)


def _message(payload: dict, *, subject: str) -> SimpleNamespace:
    return SimpleNamespace(data=json.dumps(payload).encode(), subject=subject)


def _runtime() -> NodeAgentRuntime:
    runtime = NodeAgentRuntime(NatsConfig(enabled=True))
    runtime._nats = SimpleNamespace(
        ensure_stream=AsyncMock(),
        publish_jetstream=AsyncMock(),
        pull_subscribe=AsyncMock(),
        fetch_messages=AsyncMock(),
        close=AsyncMock(),
        connect=AsyncMock(),
    )
    return runtime


def _session(*, has_pending_writes: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        has_pending_writes=lambda: has_pending_writes,
    )


def _session_maker(session):
    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx


@pytest.mark.asyncio
async def test_ensure_topology_includes_ack_subjects():
    runtime = _runtime()

    await runtime._ensure_topology()

    result_call = runtime._nats.ensure_stream.await_args_list[1].kwargs
    control_call = runtime._nats.ensure_stream.await_args_list[2].kwargs
    assert "agent.placement_results.*.acks" in result_call["subjects"]
    assert "agent.sync_reports.*.acks" in control_call["subjects"]


@pytest.mark.asyncio
async def test_handle_result_message_publishes_ack_for_duplicate(monkeypatch):
    runtime = _runtime()
    node_id = uuid4()
    event = PlacementApplyResultEvent(
        node_id=str(node_id),
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        snapshot_id="snap-1",
        epoch=2,
        event_id="placement-result:1",
        placement_id=str(uuid4()),
        op_version=7,
        applied_state=TransportAppliedState.applied,
    )
    session = _session(has_pending_writes=False)
    event_log_repo = SimpleNamespace(record_if_new=AsyncMock(return_value=False))

    monkeypatch.setattr(
        "services.nodes.agent.runtime.AsyncDatabase.get_session_maker",
        lambda: _session_maker(session),
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.NodeTransportEventLogRepository",
        lambda _: event_log_repo,
    )
    node_mock = SimpleNamespace(id=node_id)
    monkeypatch.setattr(
        "services.nodes.agent.runtime.VpnNodeRepository",
        lambda _: SimpleNamespace(get_by_id=AsyncMock(return_value=node_mock)),
    )

    should_ack = await runtime._handle_result_message(
        _message(event.model_dump(mode="json"), subject="agent.placement_results.node.results")
    )

    assert should_ack is True
    session.rollback.assert_awaited_once()
    publish_kwargs = runtime._nats.publish_jetstream.await_args.kwargs
    assert publish_kwargs["subject"] == f"agent.placement_results.{node_id}.acks"
    assert publish_kwargs["payload"]["status"] == "skipped_idempotent"
    assert publish_kwargs["payload"]["event_id"] == event.event_id


@pytest.mark.asyncio
async def test_handle_result_message_publishes_apply_ack_after_commit(monkeypatch):
    runtime = _runtime()
    node_id = uuid4()
    placement_id = uuid4()
    event = PlacementApplyResultEvent(
        node_id=str(node_id),
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        snapshot_id="snap-1",
        epoch=2,
        event_id="placement-result:2",
        placement_id=str(placement_id),
        op_version=9,
        applied_state=TransportAppliedState.applied,
    )
    session = _session(has_pending_writes=True)
    event_log_repo = SimpleNamespace(record_if_new=AsyncMock(return_value=True))
    state_repo = SimpleNamespace(touch_result=AsyncMock())
    node_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id=node_id)))
    apply_service = SimpleNamespace(apply_result=AsyncMock(return_value="applied"))

    monkeypatch.setattr(
        "services.nodes.agent.runtime.AsyncDatabase.get_session_maker",
        lambda: _session_maker(session),
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.NodeTransportEventLogRepository",
        lambda _: event_log_repo,
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.NodeTransportStateRepository",
        lambda _: state_repo,
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.VpnNodeRepository",
        lambda _: node_repo,
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.PlacementApplyService",
        lambda _: apply_service,
    )
    monkeypatch.setattr(runtime, "_resolve_node", AsyncMock(return_value=True))

    should_ack = await runtime._handle_result_message(
        _message(event.model_dump(mode="json"), subject="agent.placement_results.node.results")
    )

    assert should_ack is True
    apply_service.apply_result.assert_awaited_once()
    state_repo.touch_result.assert_awaited_once()
    session.commit.assert_awaited_once()
    publish_kwargs = runtime._nats.publish_jetstream.await_args.kwargs
    assert publish_kwargs["subject"] == f"agent.placement_results.{node_id}.acks"
    assert publish_kwargs["payload"]["status"] == "applied"


@pytest.mark.asyncio
async def test_handle_sync_report_publishes_skipped_ack_after_debounce(monkeypatch):
    runtime = _runtime()
    node_id = uuid4()
    event = SyncReportEvent(
        event_id="sync-report:1",
        node_id=str(node_id),
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        synced_count=4,
        config_version=9,
        inventory_hash="sha256:test",
        inventory_count=4,
        full_resync_completed=True,
    )
    session = _session(has_pending_writes=True)
    state_repo = SimpleNamespace(touch_sync_report=AsyncMock())
    node_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id=node_id)))
    node_service = SimpleNamespace(handle_sync_report=AsyncMock(return_value=False))

    monkeypatch.setattr(
        "services.nodes.agent.runtime.AsyncDatabase.get_session_maker",
        lambda: _session_maker(session),
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.NodeTransportStateRepository",
        lambda _: state_repo,
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.VpnNodeRepository",
        lambda _: node_repo,
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.VpnNodeService",
        lambda _: node_service,
    )

    should_ack = await runtime._handle_sync_report_message(
        _message(event.model_dump(mode="json"), subject="agent.sync_reports.node.events")
    )

    assert should_ack is True
    session.commit.assert_awaited_once()
    publish_kwargs = runtime._nats.publish_jetstream.await_args.kwargs
    assert publish_kwargs["subject"] == f"agent.sync_reports.{node_id}.acks"
    assert publish_kwargs["msg_id"].startswith(f"sync-report-ack:{event.event_id}:")
    assert publish_kwargs["payload"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_handle_sync_report_unknown_node_publishes_error_ack(monkeypatch):
    runtime = _runtime()
    node_id = uuid4()
    event = SyncReportEvent(
        event_id="sync-report:unknown",
        node_id=str(node_id),
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        synced_count=1,
        config_version=1,
        inventory_hash="sha256:test",
        inventory_count=1,
        full_resync_completed=False,
    )
    session = _session(has_pending_writes=False)
    node_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=None))

    monkeypatch.setattr(
        "services.nodes.agent.runtime.AsyncDatabase.get_session_maker",
        lambda: _session_maker(session),
    )
    monkeypatch.setattr(
        "services.nodes.agent.runtime.VpnNodeRepository",
        lambda _: node_repo,
    )

    should_ack = await runtime._handle_sync_report_message(
        _message(event.model_dump(mode="json"), subject="agent.sync_reports.node.events")
    )

    assert should_ack is True
    session.rollback.assert_awaited_once()
    publish_kwargs = runtime._nats.publish_jetstream.await_args.kwargs
    assert publish_kwargs["subject"] == f"agent.sync_reports.{node_id}.acks"
    assert publish_kwargs["msg_id"].startswith(f"sync-report-ack:{event.event_id}:")
    assert publish_kwargs["payload"]["status"] == "skipped"
    assert publish_kwargs["payload"]["error"] == "unknown_node"


@pytest.mark.asyncio
async def test_runtime_acquires_singleton_leader_lock(monkeypatch):
    runtime = _runtime()
    connection = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar=lambda: True)),
        close=AsyncMock(),
    )
    engine = SimpleNamespace(connect=AsyncMock(return_value=connection))
    monkeypatch.setattr("services.nodes.agent.runtime.AsyncDatabase.engine", engine)

    acquired = await runtime._try_acquire_leader_lock()

    assert acquired is True
    assert runtime._leader_connection is connection
    connection.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_releases_connection_when_leader_lock_busy(monkeypatch):
    runtime = _runtime()
    connection = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar=lambda: False)),
        close=AsyncMock(),
    )
    engine = SimpleNamespace(connect=AsyncMock(return_value=connection))
    monkeypatch.setattr("services.nodes.agent.runtime.AsyncDatabase.engine", engine)

    acquired = await runtime._try_acquire_leader_lock()

    assert acquired is False
    assert runtime._leader_connection is None
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_stays_standby_without_leader_lock(monkeypatch):
    runtime = _runtime()
    runtime._running = True
    runtime._try_acquire_leader_lock = AsyncMock(return_value=False)
    runtime._activate_runtime = AsyncMock()
    monkeypatch.setattr(runtime, "_has_leader_lock", MagicMock(return_value=False))
    monkeypatch.setattr("services.nodes.agent.runtime.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError))

    with pytest.raises(asyncio.CancelledError):
        await runtime._run_leader_loop()

    runtime._activate_runtime.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_activates_after_leader_lock(monkeypatch):
    runtime = _runtime()
    runtime._running = True
    runtime._leader_connection = SimpleNamespace(execute=AsyncMock(), close=AsyncMock())
    runtime._try_acquire_leader_lock = AsyncMock(return_value=True)

    async def _activate():
        runtime._running = False

    runtime._activate_runtime = AsyncMock(side_effect=_activate)
    monkeypatch.setattr(runtime, "_has_leader_lock", MagicMock(side_effect=[False, True]))
    monkeypatch.setattr("services.nodes.agent.runtime.asyncio.sleep", AsyncMock())

    await runtime._run_leader_loop()

    runtime._activate_runtime.assert_awaited_once()
