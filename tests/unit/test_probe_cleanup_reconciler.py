from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.config import ProbeConfig
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


def _probe_settings(**overrides) -> ProbeConfig:
    data = {
        "target_port": 443,
        "retention_days": 30,
        "cleanup_enabled": True,
        "cleanup_tick_sec": 600,
        "auto_route_health_enabled": True,
        "route_block_cooldown_hours": 6,
        "auto_drain_migrate_enabled": False,
        "auto_drain_tick_sec": 60,
        "auto_drain_source": "ru-probe-1",
        "auto_drain_require_recent_failure": True,
        "auto_drain_max_probe_age_sec": 600,
        "auto_drain_min_consecutive_failures": 2,
        "auto_drain_include_already_draining": False,
        "auto_drain_max_nodes": 20,
        "auto_drain_target_backend_id": None,
        "auto_drain_last_migration_reason": "probe_auto_failure",
    }
    data.update(overrides)
    return ProbeConfig(**data)


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

    reconciler = ProbeSignalCleanupReconciler(
        probe_settings=_probe_settings(),
        tick_lock=_TickLock(acquired=True),
    )
    reconciler._session_maker = _SessionMaker(session)

    out = await reconciler.run_once()

    assert out == 17
    delete_older_than.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_returns_none_when_disabled():
    session = AsyncMock()
    reconciler = ProbeSignalCleanupReconciler(
        probe_settings=_probe_settings(cleanup_enabled=False),
        tick_lock=_TickLock(acquired=True),
    )
    reconciler._session_maker = _SessionMaker(session)

    out = await reconciler.run_once()

    assert out is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_skips_when_tick_lock_not_acquired():
    session = AsyncMock()
    reconciler = ProbeSignalCleanupReconciler(
        probe_settings=_probe_settings(),
        tick_lock=_TickLock(acquired=False),
    )
    reconciler._session_maker = _SessionMaker(session)

    out = await reconciler.run_once()

    assert out is None
    session.commit.assert_not_awaited()
