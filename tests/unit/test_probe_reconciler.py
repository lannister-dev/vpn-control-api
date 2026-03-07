from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.config import ProbeConfig
from services.probe.reconciler import ProbeAutoDrainReconciler
from services.probe.schemas import ProbeAutoDrainMigrateOut


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
        "auto_route_health_enabled": True,
        "route_block_cooldown_hours": 6,
        "auto_drain_migrate_enabled": True,
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
async def test_run_once_executes_auto_drain_and_commits():
    session = AsyncMock()
    service = SimpleNamespace(
        auto_drain_and_migrate_backends=AsyncMock(
            return_value=ProbeAutoDrainMigrateOut(
                processed=2,
                migrated=1,
                skipped=1,
                dry_run=False,
                items=[],
            )
        )
    )
    reconciler = ProbeAutoDrainReconciler(
        probe_settings=_probe_settings(),
        session_maker=_SessionMaker(session),
        service_factory=lambda _: service,
    )

    out = await reconciler.run_once()

    assert out is not None
    assert out.processed == 2
    service.auto_drain_and_migrate_backends.assert_awaited_once()
    payload = service.auto_drain_and_migrate_backends.await_args.args[0]
    assert payload.source == "ru-probe-1"
    assert payload.dry_run is False
    assert payload.max_nodes == 20
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_returns_none_when_disabled():
    session = AsyncMock()
    service = SimpleNamespace(auto_drain_and_migrate_backends=AsyncMock())
    reconciler = ProbeAutoDrainReconciler(
        probe_settings=_probe_settings(auto_drain_migrate_enabled=False),
        session_maker=_SessionMaker(session),
        service_factory=lambda _: service,
    )

    out = await reconciler.run_once()

    assert out is None
    service.auto_drain_and_migrate_backends.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_ignores_invalid_target_backend_id():
    session = AsyncMock()
    service = SimpleNamespace(
        auto_drain_and_migrate_backends=AsyncMock(
            return_value=ProbeAutoDrainMigrateOut(
                processed=1,
                migrated=0,
                skipped=1,
                dry_run=False,
                items=[],
            )
        )
    )
    reconciler = ProbeAutoDrainReconciler(
        probe_settings=_probe_settings(auto_drain_target_backend_id=f"{uuid4()}-bad"),
        session_maker=_SessionMaker(session),
        service_factory=lambda _: service,
    )

    await reconciler.run_once()

    payload = service.auto_drain_and_migrate_backends.await_args.args[0]
    assert payload.target_backend_id is None


@pytest.mark.asyncio
async def test_run_once_skips_when_tick_lock_not_acquired():
    session = AsyncMock()
    service = SimpleNamespace(auto_drain_and_migrate_backends=AsyncMock())
    reconciler = ProbeAutoDrainReconciler(
        probe_settings=_probe_settings(),
        session_maker=_SessionMaker(session),
        service_factory=lambda _: service,
        tick_lock=_TickLock(acquired=False),
    )

    out = await reconciler.run_once()

    assert out is not None
    assert out.processed == 0
    service.auto_drain_and_migrate_backends.assert_not_awaited()
    session.commit.assert_not_awaited()
