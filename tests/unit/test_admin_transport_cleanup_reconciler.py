from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.admin_transport.cleanup_reconciler import AdminTransportCleanupReconciler
from services.config import TransportConfig


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


def _transport_settings(**overrides) -> TransportConfig:
    data = {
        "cleanup_enabled": True,
        "cleanup_tick_sec": 600,
        "retention_days": 30,
    }
    data.update(overrides)
    return TransportConfig(**data)


@pytest.mark.asyncio
async def test_run_once_cleans_and_commits(monkeypatch):
    session = AsyncMock()
    delete_outbox = AsyncMock(return_value=11)
    delete_events = AsyncMock(return_value=17)

    class _Repo:
        def __init__(self, _session):
            self._session = _session

        async def delete_published_outbox_older_than(self, *, cutoff):
            return await delete_outbox(cutoff=cutoff)

        async def delete_events_older_than(self, *, cutoff):
            return await delete_events(cutoff=cutoff)

    monkeypatch.setattr(
        "services.admin_transport.cleanup_reconciler.AdminTransportRepository",
        _Repo,
    )

    reconciler = AdminTransportCleanupReconciler(
        transport_settings=_transport_settings(),
        tick_lock=_TickLock(acquired=True),
    )
    reconciler._session_maker = _SessionMaker(session)

    out = await reconciler.run_once()

    assert out == (11, 17)
    delete_outbox.assert_awaited_once()
    delete_events.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_returns_none_when_disabled():
    session = AsyncMock()
    reconciler = AdminTransportCleanupReconciler(
        transport_settings=_transport_settings(cleanup_enabled=False),
        tick_lock=_TickLock(acquired=True),
    )
    reconciler._session_maker = _SessionMaker(session)

    out = await reconciler.run_once()

    assert out is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_skips_when_tick_lock_not_acquired():
    session = AsyncMock()
    reconciler = AdminTransportCleanupReconciler(
        transport_settings=_transport_settings(),
        tick_lock=_TickLock(acquired=False),
    )
    reconciler._session_maker = _SessionMaker(session)

    out = await reconciler.run_once()

    assert out is None
    session.commit.assert_not_awaited()
