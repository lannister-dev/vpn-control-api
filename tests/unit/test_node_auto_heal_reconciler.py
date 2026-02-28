from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.config import NodeAgentConfig
from services.nodes.auto_heal_service import NodeAutoHealTickOut
from services.nodes.reconciler import NodePlacementReconciler


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


def _node_settings(**overrides) -> NodeAgentConfig:
    data = {
        "sync_report_debounce_sec": 10,
        "bootstrap_allow_create": True,
        "stale_after_sec": 90,
        "auto_heal_enabled": True,
        "auto_heal_tick_sec": 60,
        "auto_heal_max_nodes": 20,
    }
    data.update(overrides)
    return NodeAgentConfig(**data)


@pytest.mark.asyncio
async def test_run_once_executes_and_commits():
    session = AsyncMock()
    service = SimpleNamespace(
        run_once=AsyncMock(
            return_value=NodeAutoHealTickOut(
                processed_nodes=1,
                drained_nodes=1,
                migrated_nodes=1,
                migrated_placements=12,
                skipped_nodes=0,
                orphan_active_placements=12,
            )
        )
    )

    reconciler = NodePlacementReconciler(
        node_settings=_node_settings(),
        session_maker=_SessionMaker(session),
        service_factory=lambda *_: service,
    )

    out = await reconciler.run_once()

    assert out is not None
    assert out.migrated_placements == 12
    service.run_once.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_returns_none_when_disabled():
    session = AsyncMock()
    service = SimpleNamespace(run_once=AsyncMock())
    reconciler = NodePlacementReconciler(
        node_settings=_node_settings(auto_heal_enabled=False),
        session_maker=_SessionMaker(session),
        service_factory=lambda *_: service,
    )

    out = await reconciler.run_once()

    assert out is None
    service.run_once.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_skips_when_tick_lock_not_acquired():
    session = AsyncMock()
    service = SimpleNamespace(run_once=AsyncMock())
    reconciler = NodePlacementReconciler(
        node_settings=_node_settings(),
        session_maker=_SessionMaker(session),
        service_factory=lambda *_: service,
        tick_lock=_TickLock(acquired=False),
    )

    out = await reconciler.run_once()

    assert out is not None
    assert out.processed_nodes == 0
    service.run_once.assert_not_awaited()
    session.commit.assert_not_awaited()
