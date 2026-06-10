from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from services.nodes.reconcilers.upstream_failover import UpstreamFailoverReconciler


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


def _entry(*, upstream_id):
    return SimpleNamespace(
        id=uuid4(),
        name=f"entry-{uuid4().hex[:6]}",
        upstream_node_id=upstream_id,
    )


def _backend():
    return SimpleNamespace(
        id=uuid4(),
        name=f"backend-{uuid4().hex[:6]}",
        is_enabled=True,
        is_draining=False,
        is_active=True,
    )


def _repo_patch(dead, live):
    return patch(
        "services.nodes.reconcilers.upstream_failover.VpnNodeRepository",
        return_value=SimpleNamespace(
            list_entries_with_dead_upstream=AsyncMock(return_value=dead),
            list_live_backends=AsyncMock(return_value=live),
        ),
    )


@pytest.mark.asyncio
async def test_run_once_no_dead_entries_returns_zero():
    session = AsyncMock()
    route_service = SimpleNamespace(sync_entry_upstream=AsyncMock())
    with _repo_patch(dead=[], live=[_backend()]):
        reconciler = UpstreamFailoverReconciler(
            session_maker=_SessionMaker(session),
            route_service_factory=lambda _: route_service,
        )
        applied = await reconciler.run_once()
    assert applied == 0
    route_service.sync_entry_upstream.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_no_live_backends_skips():
    session = AsyncMock()
    route_service = SimpleNamespace(sync_entry_upstream=AsyncMock())
    with _repo_patch(dead=[_entry(upstream_id=uuid4())], live=[]):
        reconciler = UpstreamFailoverReconciler(
            session_maker=_SessionMaker(session),
            route_service_factory=lambda _: route_service,
        )
        applied = await reconciler.run_once()
    assert applied == 0
    route_service.sync_entry_upstream.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_resyncs_dead_entries_to_live_backend():
    session = AsyncMock()
    route_service = SimpleNamespace(sync_entry_upstream=AsyncMock())
    dead = [_entry(upstream_id=uuid4()), _entry(upstream_id=uuid4())]
    live = [_backend(), _backend()]
    with _repo_patch(dead=dead, live=live):
        reconciler = UpstreamFailoverReconciler(
            session_maker=_SessionMaker(session),
            route_service_factory=lambda _: route_service,
        )
        applied = await reconciler.run_once()

    assert applied == 2
    assert route_service.sync_entry_upstream.await_count == 2
    for call in route_service.sync_entry_upstream.await_args_list:
        assert call.kwargs["backend_node_id"] == live[0].id
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_run_once_triggers_snapshot_for_each_failed_over_entry():
    session = AsyncMock()
    route_service = SimpleNamespace(sync_entry_upstream=AsyncMock())
    dead = [_entry(upstream_id=uuid4()), _entry(upstream_id=uuid4())]
    snapshot_trigger = AsyncMock()
    with _repo_patch(dead=dead, live=[_backend()]):
        reconciler = UpstreamFailoverReconciler(
            session_maker=_SessionMaker(session),
            route_service_factory=lambda _: route_service,
            snapshot_trigger=snapshot_trigger,
        )
        applied = await reconciler.run_once()

    assert applied == 2
    assert snapshot_trigger.await_count == 2
    triggered_ids = {call.kwargs["node_id"] for call in snapshot_trigger.await_args_list}
    assert triggered_ids == {dead[0].id, dead[1].id}
    for call in snapshot_trigger.await_args_list:
        assert call.kwargs["reason"] == "upstream_failover"


@pytest.mark.asyncio
async def test_run_once_snapshot_failure_does_not_break_failover():
    session = AsyncMock()
    route_service = SimpleNamespace(sync_entry_upstream=AsyncMock())
    dead = [_entry(upstream_id=uuid4())]
    snapshot_trigger = AsyncMock(side_effect=RuntimeError("nats down"))
    with _repo_patch(dead=dead, live=[_backend()]):
        reconciler = UpstreamFailoverReconciler(
            session_maker=_SessionMaker(session),
            route_service_factory=lambda _: route_service,
            snapshot_trigger=snapshot_trigger,
        )
        applied = await reconciler.run_once()

    assert applied == 1
    session.commit.assert_awaited()
