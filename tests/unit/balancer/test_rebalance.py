from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.balancer.rebalance import BackendRebalancer


def _backend(name):
    b = MagicMock()
    b.id = uuid4()
    b.name = name
    b.capacity = 1000
    return b


def _key(tag):
    k = MagicMock()
    k.id = uuid4()
    k.entry_routing_override_backend_tag = tag
    return k


def _make_rebalancer():
    rb = BackendRebalancer.__new__(BackendRebalancer)
    rb._session = MagicMock()
    rb._nats = None
    rb._node_repository = MagicMock()
    rb._key_repository = MagicMock()
    rb._placement_repository = MagicMock()
    rb._transport = MagicMock()
    rb._transport.enqueue_for_key_state = AsyncMock()
    rb._key_repository.update_by_id = AsyncMock()
    cfg = MagicMock()
    cfg.traffic_window_min = 15
    cfg.weight_bandwidth = 0.5
    cfg.weight_cpu = 0.3
    cfg.weight_conn = 0.2
    cfg.score_spread_threshold = 0.15
    cfg.move_cap = 15
    cfg.move_cooldown_sec = 1200
    rb._cfg = cfg
    rb._cpu_by_backend = AsyncMock(return_value={})
    return rb


def _wire(rb, *, backends, keys, eligible, selected, bytes_by_key):
    rb._node_repository.list_live_backends = AsyncMock(return_value=backends)
    rb._key_repository.list_all_active = AsyncMock(return_value=keys)
    rb._placement_repository.map_active_backend_nodes_by_key = AsyncMock(return_value=eligible)
    rb._placement_repository.map_selected_backend_by_key = AsyncMock(return_value=selected)
    rb._recent_bytes_by_key = AsyncMock(return_value=bytes_by_key)


@pytest.mark.asyncio
async def test_unpinned_heavy_key_is_moved_off_hot_backend():
    hot, cold = _backend("hot"), _backend("cold")
    whale = _key(None)  # unpinned — old code skipped these entirely
    rb = _make_rebalancer()
    _wire(rb, backends=[hot, cold], keys=[whale],
          eligible={whale.id: {hot.id, cold.id}}, selected={whale.id: hot.id},
          bytes_by_key={whale.id: 500_000_000})

    moved = await rb.rebalance()

    assert moved == [whale.id]
    args, _ = rb._key_repository.update_by_id.call_args
    assert args[0] == whale.id
    assert args[1]["entry_routing_override_backend_tag"] == "backend-cold"


@pytest.mark.asyncio
async def test_no_move_when_key_ineligible_on_other_backend():
    hot, cold = _backend("hot"), _backend("cold")
    whale = _key(None)
    rb = _make_rebalancer()
    _wire(rb, backends=[hot, cold], keys=[whale],
          eligible={whale.id: {hot.id}}, selected={whale.id: hot.id},
          bytes_by_key={whale.id: 500_000_000})

    moved = await rb.rebalance()

    assert moved == []
    rb._key_repository.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_key_in_cooldown_is_not_moved():
    hot, cold = _backend("hot"), _backend("cold")
    whale = _key(None)
    rb = _make_rebalancer()
    _wire(rb, backends=[hot, cold], keys=[whale],
          eligible={whale.id: {hot.id, cold.id}}, selected={whale.id: hot.id},
          bytes_by_key={whale.id: 500_000_000})

    # whale is in cooldown -> must not be moved even though it is the hottest
    moved = await rb.rebalance(cooldown_key_ids=frozenset({whale.id}))

    assert moved == []
    rb._key_repository.update_by_id.assert_not_awaited()
