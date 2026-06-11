from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.nodes.reconcilers.snapshot_freshness import (
    SETTLE_SEC,
    NodeSnapshotFreshnessReconciler,
)


def _ago(seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _SessionContext(self._session)


def _node(role="backend"):
    return SimpleNamespace(id=uuid4(), role=role, name=f"node-{uuid4().hex[:6]}")


def _row(*, key_updated: datetime, placement_created: datetime):
    return (
        SimpleNamespace(created_at=placement_created),
        SimpleNamespace(updated_at=key_updated),
    )


def _session(*, nodes, last_snapshots):
    session = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=nodes)
    session.scalars = AsyncMock(return_value=scalars_result)
    session.scalar = AsyncMock(side_effect=last_snapshots)
    return session


def _patch_rows(rows):
    return patch(
        "services.nodes.reconcilers.snapshot_freshness.UserPlacementRepository",
        return_value=SimpleNamespace(
            list_transport_rows_for_entry=AsyncMock(return_value=rows),
            list_transport_rows_for_backend=AsyncMock(return_value=rows),
        ),
    )


@pytest.mark.asyncio
async def test_drift_triggers_snapshot():
    node = _node("backend")
    # desired changed 120s ago (> settle), last snapshot 600s ago -> behind
    rows = [_row(key_updated=_ago(120), placement_created=_ago(300))]
    session = _session(nodes=[node], last_snapshots=[_ago(600)])
    trigger = AsyncMock()
    with _patch_rows(rows):
        rec = NodeSnapshotFreshnessReconciler(session_maker=_SessionMaker(session), snapshot_trigger=trigger)
        count = await rec.run_once()
    assert count == 1
    trigger.assert_awaited_once()
    assert trigger.await_args.kwargs["node_id"] == node.id
    assert trigger.await_args.kwargs["reason"] == "freshness_drift"


@pytest.mark.asyncio
async def test_no_drift_when_snapshot_newer_than_change():
    node = _node("entry")
    rows = [_row(key_updated=_ago(600), placement_created=_ago(700))]
    session = _session(nodes=[node], last_snapshots=[_ago(120)])  # snapshot newer than change
    trigger = AsyncMock()
    with _patch_rows(rows):
        rec = NodeSnapshotFreshnessReconciler(session_maker=_SessionMaker(session), snapshot_trigger=trigger)
        count = await rec.run_once()
    assert count == 0
    trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_recent_change_is_left_to_settle():
    node = _node("backend")
    # change only SETTLE_SEC/2 ago -> still settling, don't snapshot yet
    rows = [_row(key_updated=_ago(max(1, SETTLE_SEC // 2)), placement_created=_ago(300))]
    session = _session(nodes=[node], last_snapshots=[_ago(600)])
    trigger = AsyncMock()
    with _patch_rows(rows):
        rec = NodeSnapshotFreshnessReconciler(session_maker=_SessionMaker(session), snapshot_trigger=trigger)
        count = await rec.run_once()
    assert count == 0
    trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_node_never_snapshotted_triggers():
    node = _node("backend")
    rows = [_row(key_updated=_ago(120), placement_created=_ago(300))]
    session = _session(nodes=[node], last_snapshots=[None])  # no prior snapshot
    trigger = AsyncMock()
    with _patch_rows(rows):
        rec = NodeSnapshotFreshnessReconciler(session_maker=_SessionMaker(session), snapshot_trigger=trigger)
        count = await rec.run_once()
    assert count == 1
    trigger.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_trigger_configured_is_noop():
    rec = NodeSnapshotFreshnessReconciler(session_maker=_SessionMaker(MagicMock()), snapshot_trigger=None)
    assert await rec.run_once() == 0


@pytest.mark.asyncio
async def test_trigger_failure_does_not_break_loop():
    n1, n2 = _node("backend"), _node("backend")
    rows = [_row(key_updated=_ago(120), placement_created=_ago(300))]
    session = _session(nodes=[n1, n2], last_snapshots=[_ago(600), _ago(600)])
    trigger = AsyncMock(side_effect=RuntimeError("nats down"))
    with _patch_rows(rows):
        rec = NodeSnapshotFreshnessReconciler(session_maker=_SessionMaker(session), snapshot_trigger=trigger)
        count = await rec.run_once()
    assert count == 2
    assert trigger.await_count == 2
