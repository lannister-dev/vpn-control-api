from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.probe.cleanup_reconciler import ProbeSignalCleanupReconciler


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
        "services.probe.cleanup_reconciler.ProbePolicyRepository",
        return_value=SimpleNamespace(get_current=AsyncMock(return_value=policy)),
    )


@pytest.mark.asyncio
async def test_run_once_cleans_and_commits(monkeypatch):
    session = AsyncMock()
    delete_older_than = AsyncMock(return_value=17)

    class _Repo:
        def __init__(self, _session):
            self._session = _session

        async def delete_older_than(self, *, cutoff):
            return await delete_older_than(cutoff=cutoff)

    monkeypatch.setattr(
        "services.probe.cleanup_reconciler.ProbeSignalRepository",
        _Repo,
    )

    with _policy_repo_patch(_policy()):
        reconciler = ProbeSignalCleanupReconciler(tick_lock=_TickLock(acquired=True))
        reconciler._session_maker = _SessionMaker(session)
        out = await reconciler.run_once()

    assert out == 17
    delete_older_than.assert_awaited_once()
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_run_once_returns_none_when_disabled():
    session = AsyncMock()
    with _policy_repo_patch(_policy(cleanup_enabled=False)):
        reconciler = ProbeSignalCleanupReconciler(tick_lock=_TickLock(acquired=True))
        reconciler._session_maker = _SessionMaker(session)
        out = await reconciler.run_once()

    assert out is None


@pytest.mark.asyncio
async def test_run_once_skips_when_tick_lock_not_acquired():
    session = AsyncMock()
    with _policy_repo_patch(_policy()):
        reconciler = ProbeSignalCleanupReconciler(tick_lock=_TickLock(acquired=False))
        reconciler._session_maker = _SessionMaker(session)
        out = await reconciler.run_once()

    assert out is None
