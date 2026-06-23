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
    rb._placement_repository.sticky_key_ids = AsyncMock(return_value=set())
    rb._placement_repository.set_sticky_until_for_key = AsyncMock()
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


@pytest.mark.asyncio
async def test_unpinned_heavy_key_is_moved_off_hot_backend():
    hot, cold = _backend("hot"), _backend("cold")
    whale = _key(None)  # unpinned — old code skipped these entirely

    rb = _make_rebalancer()
    rb._node_repository.list_live_backends = AsyncMock(return_value=[hot, cold])
    rb._key_repository.list_all_active = AsyncMock(return_value=[whale])
    rb._placement_repository.map_active_backend_nodes_by_key = AsyncMock(
        return_value={whale.id: {hot.id, cold.id}},
    )
    rb._placement_repository.map_selected_backend_by_key = AsyncMock(
        return_value={whale.id: hot.id},  # effective backend = hot
    )
    rb._recent_bytes_by_key = AsyncMock(return_value={whale.id: 500_000_000})

    moved = await rb.rebalance()

    assert moved == 1
    rb._key_repository.update_by_id.assert_awaited_once()
    args, _ = rb._key_repository.update_by_id.call_args
    assert args[0] == whale.id
    assert args[1]["entry_routing_override_backend_tag"] == "backend-cold"
    rb._placement_repository.set_sticky_until_for_key.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_move_when_key_ineligible_on_other_backend():
    hot, cold = _backend("hot"), _backend("cold")
    whale = _key(None)

    rb = _make_rebalancer()
    rb._node_repository.list_live_backends = AsyncMock(return_value=[hot, cold])
    rb._key_repository.list_all_active = AsyncMock(return_value=[whale])
    rb._placement_repository.map_active_backend_nodes_by_key = AsyncMock(
        return_value={whale.id: {hot.id}},  # only eligible on hot
    )
    rb._placement_repository.map_selected_backend_by_key = AsyncMock(
        return_value={whale.id: hot.id},
    )
    rb._recent_bytes_by_key = AsyncMock(return_value={whale.id: 500_000_000})

    moved = await rb.rebalance()

    assert moved == 0
    rb._key_repository.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_sticky_key_in_cooldown_is_not_moved():
    hot, cold = _backend("hot"), _backend("cold")
    whale = _key(None)

    rb = _make_rebalancer()
    rb._node_repository.list_live_backends = AsyncMock(return_value=[hot, cold])
    rb._key_repository.list_all_active = AsyncMock(return_value=[whale])
    rb._placement_repository.map_active_backend_nodes_by_key = AsyncMock(
        return_value={whale.id: {hot.id, cold.id}},
    )
    rb._placement_repository.map_selected_backend_by_key = AsyncMock(
        return_value={whale.id: hot.id},
    )
    # key is in cooldown -> must not be moved even though it is the hottest
    rb._placement_repository.sticky_key_ids = AsyncMock(return_value={whale.id})
    rb._recent_bytes_by_key = AsyncMock(return_value={whale.id: 500_000_000})

    moved = await rb.rebalance()

    assert moved == 0
    rb._key_repository.update_by_id.assert_not_awaited()
