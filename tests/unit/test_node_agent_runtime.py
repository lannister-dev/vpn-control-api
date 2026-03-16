import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
    monkeypatch.setattr(runtime, "_resolve_node", AsyncMock(return_value=True))

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
    event_log_repo = SimpleNamespace(record_if_new=AsyncMock(return_value=True))
    state_repo = SimpleNamespace(touch_sync_report=AsyncMock())
    node_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id=node_id)))
    node_service = SimpleNamespace(handle_sync_report=AsyncMock(return_value=False))

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
    assert publish_kwargs["payload"]["status"] == "skipped"


def test_heartbeat_event_id_passthrough():
    event = HeartbeatEvent(
        event_id="heartbeat:node-1:7",
        node_id="node-1",
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        agent_version="1.0.0",
        is_healthy=True,
        ready=True,
        poll_count=7,
        applied=2,
        failed=0,
    )

    assert NodeAgentRuntime._heartbeat_event_id(event) == event.event_id
