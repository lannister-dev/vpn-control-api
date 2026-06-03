from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from services.balancer.service import BalancerService
from services.balancer.types import KeyLoad, NodeLoad
from services.config import BalancerConfig


def _cfg():
    return BalancerConfig(enabled=True, dead_zone=0.05, move_fraction=1.0, max_moves_per_tick=50)


class _FakeCtx:
    async def __aenter__(self):
        return AsyncMock()

    async def __aexit__(self, *a):
        return False


def _session_maker():
    return lambda: _FakeCtx()


async def test_service_noop_under_two_nodes():
    repo = AsyncMock()
    repo.load_nodes.return_value = [NodeLoad(uuid4(), "lon", 1000, 0, 10, 100)]
    with patch("services.balancer.service.BalancerRepository", return_value=repo):
        plan = await BalancerService(config=_cfg(), session_maker=_session_maker()).run_once()
    assert plan.is_noop
    repo.apply_moves.assert_not_called()


async def test_service_applies_bootstrap_moves():
    lon, zrh = uuid4(), uuid4()
    repo = AsyncMock()
    repo.load_nodes.return_value = [
        NodeLoad(lon, "lon", 10_000, 20, 10, 100),
        NodeLoad(zrh, "zrh", 0, 0, 10, 100),
    ]
    repo.load_keys.return_value = [
        KeyLoad(uuid4(), 500, lon, frozenset([lon, zrh])) for _ in range(10)
    ]
    with patch("services.balancer.service.BalancerRepository", return_value=repo):
        plan = await BalancerService(config=_cfg(), session_maker=_session_maker()).run_once()
    assert plan.moves
    assert all(m.to_backend_id == zrh for m in plan.moves)
    repo.apply_moves.assert_awaited_once()
