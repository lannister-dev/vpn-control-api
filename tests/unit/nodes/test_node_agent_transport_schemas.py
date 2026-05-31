from datetime import datetime, timezone

from services.nodes.agent.schemas import (
    AgentSubjects,
    HeartbeatEvent,
    PlacementApplyAckEvent,
    PlacementApplyResultEvent,
    PlacementCommandEvent,
    SnapshotRequestEvent,
    SnapshotRequestReason,
    SyncReportAckEvent,
    SyncReportAckStatus,
    SyncReportEvent,
    TransportAppliedState,
    TransportDesiredState,
    TransportReportStatus,
)


def test_transport_subjects_match_agent_contract():
    subjects = AgentSubjects(
        command_prefix="agent.placements",
        result_prefix="agent.placement_results",
        snapshot_prefix="agent.snapshots",
        heartbeat_prefix="agent.heartbeats",
        sync_report_prefix="agent.sync_reports",
    )

    assert subjects.placement_command("node-1") == "agent.placements.node-1.commands"
    assert subjects.placement_result("node-1") == "agent.placement_results.node-1.results"
    assert subjects.placement_result_ack("node-1") == "agent.placement_results.node-1.acks"
    assert subjects.snapshot_request("node-1") == "agent.snapshots.node-1.request"
    assert subjects.snapshot_chunk("node-1") == "agent.snapshots.node-1.chunks"
    assert subjects.heartbeat("node-1") == "agent.heartbeats.node-1.events"
    assert subjects.sync_report("node-1") == "agent.sync_reports.node-1.events"
    assert subjects.sync_report_ack("node-1") == "agent.sync_reports.node-1.acks"


def test_placement_command_schema_roundtrip():
    event = PlacementCommandEvent(
        node_id="node-1",
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        event_id="evt-1",
        placement_id="pl-1",
        key_id="key-1",
        op_version=4,
        desired_state=TransportDesiredState.active,
        backend_node_id="node-1",
        client_id="550e8400-e29b-41d4-a716-446655440000",
    )

    assert PlacementCommandEvent.model_validate(event.model_dump(mode="json")) == event


def test_placement_command_carries_entry_routing_override():
    event = PlacementCommandEvent(
        node_id="node-1",
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        event_id="evt-1",
        placement_id="pl-1",
        key_id="key-1",
        op_version=4,
        desired_state=TransportDesiredState.active,
        backend_node_id="node-1",
        client_id="550e8400-e29b-41d4-a716-446655440000",
        entry_routing_override_backend_tag="backend-zrh-backend-01",
    )

    dumped = event.model_dump(mode="json")
    assert dumped["entry_routing_override_backend_tag"] == "backend-zrh-backend-01"
    assert PlacementCommandEvent.model_validate(dumped) == event


def test_result_event_accepts_inventory_metadata():
    event = PlacementApplyResultEvent(
        node_id="node-1",
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        event_id="evt-2",
        placement_id="pl-1",
        op_version=4,
        applied_state=TransportAppliedState.applied,
        inventory_hash="abc123",
        inventory_count=1,
    )

    assert event.inventory_hash == "abc123"
    assert event.inventory_count == 1


def test_result_ack_event_roundtrip():
    event = PlacementApplyAckEvent(
        node_id="node-1",
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        snapshot_id="snap-1",
        epoch=2,
        event_id="evt-2",
        placement_id="pl-1",
        op_version=4,
        status=TransportReportStatus.skipped_idempotent,
    )

    assert PlacementApplyAckEvent.model_validate(event.model_dump(mode="json")) == event


def test_snapshot_request_schema_contains_recovery_context():
    event = SnapshotRequestEvent(
        node_id="node-1",
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        reason=SnapshotRequestReason.xray_restart,
        known_snapshot_id="snap-1",
        last_command_stream_seq=15,
        last_seen_xray_uptime=99,
    )

    assert event.reason == SnapshotRequestReason.xray_restart
    assert event.last_command_stream_seq == 15


def test_control_event_schemas_accept_runtime_payload():
    heartbeat = HeartbeatEvent(
        event_id="heartbeat:node-1:5",
        node_id="node-1",
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        agent_version="1.0.0",
        is_healthy=True,
        ready=True,
        poll_count=5,
        applied=4,
        failed=1,
    )
    sync_report = SyncReportEvent(
        event_id="sync-report:node-1:9:sha256:test:4:4:1",
        node_id="node-1",
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        synced_count=4,
        config_version=9,
        inventory_hash="sha256:test",
        inventory_count=4,
        full_resync_completed=True,
    )
    sync_ack = SyncReportAckEvent(
        event_id=sync_report.event_id,
        node_id="node-1",
        emitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status=SyncReportAckStatus.accepted,
    )

    assert heartbeat.event_id.endswith(":5")
    assert heartbeat.ready is True
    assert sync_report.full_resync_completed is True
    assert sync_ack.event_id == sync_report.event_id
