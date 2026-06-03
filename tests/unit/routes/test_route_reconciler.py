from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.routes.reconcilers.warmup import RouteWarmupReconciler


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


@pytest.mark.asyncio
async def test_run_once_skips_when_tick_lock_not_acquired():
    reconciler = RouteWarmupReconciler(tick_lock=_TickLock(acquired=False))
    reconciler.tick = AsyncMock()

    out = await reconciler.run_once()

    assert out is None
    reconciler.tick.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_once_executes_when_tick_lock_acquired():
    reconciler = RouteWarmupReconciler(tick_lock=_TickLock(acquired=True))
    tick = SimpleNamespace(processed=1, advanced=1, finalized=0)
    reconciler.tick = AsyncMock(return_value=tick)

    out = await reconciler.run_once()

    assert out is tick
    reconciler.tick.assert_awaited_once_with()
