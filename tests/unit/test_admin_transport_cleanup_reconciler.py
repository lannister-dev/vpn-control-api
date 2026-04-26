from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.admin_transport.reconcilers.cleanup import AdminTransportCleanupReconciler


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


class _LockContext:
    def __init__(self, acquired: bool):
        self._acquired = acquired

    async def __aenter__(self):
        return self._acquired

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TickLock:
    def __init__(self, acquired: bool):
        self._acquired = acquired

    def hold(self):
        return _LockContext(self._acquired)


def _policy(**overrides):
    data = dict(cleanup_enabled=True, cleanup_tick_sec=600, retention_days=30)
    data.update(overrides)
    return SimpleNamespace(**data)


def _policy_repo_patch(policy):
    return patch(
        "services.admin_transport.reconcilers.cleanup.TransportPolicyRepository",
        return_value=SimpleNamespace(list=AsyncMock(return_value=[policy])),
    )


@pytest.mark.asyncio
async def test_run_once_cleans_and_commits(monkeypatch):
    session = AsyncMock()
    delete_outbox = AsyncMock(return_value=11)
    delete_events = AsyncMock(return_value=17)
    delete_dedup = AsyncMock(return_value=5)

    class _Repo:
        def __init__(self, _session):
            self._session = _session

        async def delete_published_outbox_older_than(self, *, cutoff):
            return await delete_outbox(cutoff=cutoff)

        async def delete_events_older_than(self, *, cutoff):
            return await delete_events(cutoff=cutoff)

        async def delete_nats_dedup_older_than(self, *, cutoff):
            return await delete_dedup(cutoff=cutoff)

    monkeypatch.setattr(
        "services.admin_transport.reconcilers.cleanup.AdminTransportRepository",
        _Repo,
    )

    with _policy_repo_patch(_policy()):
        reconciler = AdminTransportCleanupReconciler(tick_lock=_TickLock(acquired=True))
        reconciler._session_maker = _SessionMaker(session)
        out = await reconciler.run_once()

    assert out == (11, 17, 5)
    delete_outbox.assert_awaited_once()
    delete_events.assert_awaited_once()
    delete_dedup.assert_awaited_once()
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_run_once_returns_none_when_disabled():
    session = AsyncMock()
    with _policy_repo_patch(_policy(cleanup_enabled=False)):
        reconciler = AdminTransportCleanupReconciler(tick_lock=_TickLock(acquired=True))
        reconciler._session_maker = _SessionMaker(session)
        out = await reconciler.run_once()

    assert out is None


@pytest.mark.asyncio
async def test_run_once_skips_when_tick_lock_not_acquired():
    session = AsyncMock()
    with _policy_repo_patch(_policy()):
        reconciler = AdminTransportCleanupReconciler(tick_lock=_TickLock(acquired=False))
        reconciler._session_maker = _SessionMaker(session)
        out = await reconciler.run_once()

    assert out is None
