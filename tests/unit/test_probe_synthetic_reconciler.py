from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.config import ProbeConfig
from services.probe.schemas import ProbeSyntheticReconcileResult
from services.probe.synthetic_reconciler import ProbeSyntheticCredentialReconciler


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
        "synthetic_reality_client_id": "probe-reality-cid",
        "synthetic_ws_client_id": "probe-ws-cid",
        "synthetic_reconcile_enabled": True,
        "synthetic_reconcile_tick_sec": 300,
        "synthetic_user_telegram_id": 900000001,
        "synthetic_user_username": "probe-synthetic",
        "synthetic_key_valid_days": 3650,
        "synthetic_key_traffic_limit_mb": 102400,
        "retention_days": 30,
        "cleanup_enabled": True,
        "cleanup_tick_sec": 600,
        "auto_route_health_enabled": True,
        "route_block_cooldown_hours": 6,
        "auto_drain_migrate_enabled": False,
        "auto_drain_tick_sec": 60,
        "auto_drain_source": None,
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
async def test_run_once_executes_and_commits():
    session = AsyncMock()
    service = SimpleNamespace(
        reconcile=AsyncMock(
            return_value=ProbeSyntheticReconcileResult(
                processed_transports=2,
                created_user=True,
                created_keys=2,
                reactivated_keys=0,
                activated_placements=3,
                deactivated_placements=1,
            )
        )
    )
    reconciler = ProbeSyntheticCredentialReconciler(
        probe_settings=_probe_settings(),
        session_maker=_SessionMaker(session),
        service_factory=lambda _: service,
    )

    out = await reconciler.run_once()

    assert out is not None
    assert out.processed_transports == 2
    service.reconcile.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_returns_none_when_disabled():
    session = AsyncMock()
    service = SimpleNamespace(reconcile=AsyncMock())
    reconciler = ProbeSyntheticCredentialReconciler(
        probe_settings=_probe_settings(synthetic_reconcile_enabled=False),
        session_maker=_SessionMaker(session),
        service_factory=lambda _: service,
    )

    out = await reconciler.run_once()

    assert out is None
    service.reconcile.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_skips_when_tick_lock_not_acquired():
    session = AsyncMock()
    service = SimpleNamespace(reconcile=AsyncMock())
    reconciler = ProbeSyntheticCredentialReconciler(
        probe_settings=_probe_settings(),
        session_maker=_SessionMaker(session),
        service_factory=lambda _: service,
        tick_lock=_TickLock(acquired=False),
    )

    out = await reconciler.run_once()

    assert out is not None
    assert out.processed_transports == 0
    service.reconcile.assert_not_awaited()
    session.commit.assert_not_awaited()
