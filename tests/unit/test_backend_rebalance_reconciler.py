from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.config import EntryRoutingConfig, NatsConfig
from services.vpn.keys.reconcilers.backend_rebalance import BackendRebalanceReconciler


def _make_reconciler(nats: AsyncMock | None = None):
    cfg = EntryRoutingConfig(enabled=True, publisher_tick_sec=5, backend_rebalance_tick_sec=60)
    nats_cfg = NatsConfig(enabled=True, server="nats://test", name="test")
    lock = MagicMock()
    lock.hold.return_value.__aenter__ = AsyncMock(return_value=True)
    lock.hold.return_value.__aexit__ = AsyncMock(return_value=False)
    nats = nats or AsyncMock()
    nats.is_connected = True
    return BackendRebalanceReconciler(
        routing_config=cfg,
        nats_config=nats_cfg,
        nats_client=nats,
        tick_lock=lock,
    )


def _make_node(*, id, name, is_enabled=True, is_draining=False):
    return SimpleNamespace(id=id, name=name, is_enabled=is_enabled, is_draining=is_draining)


def _make_key(*, id, override=None):
    return SimpleNamespace(id=id, entry_routing_override_backend_tag=override)


@pytest.mark.asyncio
async def test_picks_least_loaded_backend_and_updates(async_session):
    pra_id, lv_id = uuid4(), uuid4()
    key_id = uuid4()
    nats = AsyncMock()
    nats.is_connected = True
    # KV has Praha=58, Latvia absent (0)
    nats.kv_list_all.return_value = {
        "node.x": b'{"by_backend": {"backend-pra-backend-01": 58}}',
    }

    reconciler = _make_reconciler(nats=nats)

    mock_key_repo = AsyncMock()
    mock_key_repo.list_all_active.return_value = [
        _make_key(id=key_id, override="backend-pra-backend-01"),
    ]

    mock_placement_repo = AsyncMock()
    mock_placement_repo.map_active_backend_nodes_by_key.return_value = {
        key_id: {pra_id, lv_id},
    }

    mock_node_repo = AsyncMock()
    mock_node_repo.list_live_backends.return_value = [
        _make_node(id=pra_id, name="pra-backend-01"),
        _make_node(id=lv_id, name="rix-backend-01"),
    ]

    with patch(
        "services.vpn.keys.reconcilers.backend_rebalance.VpnKeyRepository",
        return_value=mock_key_repo,
    ), patch(
        "services.vpn.keys.reconcilers.backend_rebalance.UserPlacementRepository",
        return_value=mock_placement_repo,
    ), patch(
        "services.vpn.keys.reconcilers.backend_rebalance.VpnNodeRepository",
        return_value=mock_node_repo,
    ):
        changed = await reconciler._tick()

    assert changed == 1
    mock_key_repo.update_by_id.assert_awaited_once_with(
        key_id, {"entry_routing_override_backend_tag": "backend-rix-backend-01"},
    )


@pytest.mark.asyncio
async def test_no_update_when_override_already_optimal(async_session):
    pra_id, lv_id = uuid4(), uuid4()
    key_id = uuid4()
    nats = AsyncMock()
    nats.is_connected = True
    nats.kv_list_all.return_value = {
        "node.x": b'{"by_backend": {"backend-pra-backend-01": 58}}',
    }

    reconciler = _make_reconciler(nats=nats)

    mock_key_repo = AsyncMock()
    mock_key_repo.list_all_active.return_value = [
        _make_key(id=key_id, override="backend-rix-backend-01"),
    ]
    mock_placement_repo = AsyncMock()
    mock_placement_repo.map_active_backend_nodes_by_key.return_value = {
        key_id: {pra_id, lv_id},
    }
    mock_node_repo = AsyncMock()
    mock_node_repo.list_live_backends.return_value = [
        _make_node(id=pra_id, name="pra-backend-01"),
        _make_node(id=lv_id, name="rix-backend-01"),
    ]

    with patch(
        "services.vpn.keys.reconcilers.backend_rebalance.VpnKeyRepository",
        return_value=mock_key_repo,
    ), patch(
        "services.vpn.keys.reconcilers.backend_rebalance.UserPlacementRepository",
        return_value=mock_placement_repo,
    ), patch(
        "services.vpn.keys.reconcilers.backend_rebalance.VpnNodeRepository",
        return_value=mock_node_repo,
    ):
        changed = await reconciler._tick()

    assert changed == 0
    mock_key_repo.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_keys_without_placements(async_session):
    nats = AsyncMock()
    nats.is_connected = True
    nats.kv_list_all.return_value = {}
    reconciler = _make_reconciler(nats=nats)

    key_id = uuid4()
    mock_key_repo = AsyncMock()
    mock_key_repo.list_all_active.return_value = [_make_key(id=key_id, override=None)]
    mock_placement_repo = AsyncMock()
    mock_placement_repo.map_active_backend_nodes_by_key.return_value = {}
    mock_node_repo = AsyncMock()
    mock_node_repo.list_live_backends.return_value = [
        _make_node(id=uuid4(), name="pra-backend-01"),
    ]

    with patch(
        "services.vpn.keys.reconcilers.backend_rebalance.VpnKeyRepository",
        return_value=mock_key_repo,
    ), patch(
        "services.vpn.keys.reconcilers.backend_rebalance.UserPlacementRepository",
        return_value=mock_placement_repo,
    ), patch(
        "services.vpn.keys.reconcilers.backend_rebalance.VpnNodeRepository",
        return_value=mock_node_repo,
    ):
        changed = await reconciler._tick()

    assert changed == 0
    mock_key_repo.update_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_sequential_increment_distributes_keys(async_session):
    """When 2 keys are tied at 0, the local increment after first pick
    causes the second key to go to the OTHER backend."""
    pra_id, lv_id = uuid4(), uuid4()
    k1, k2 = uuid4(), uuid4()
    nats = AsyncMock()
    nats.is_connected = True
    # Empty KV → both backends at 0
    nats.kv_list_all.return_value = {}
    reconciler = _make_reconciler(nats=nats)

    mock_key_repo = AsyncMock()
    mock_key_repo.list_all_active.return_value = [
        _make_key(id=k1, override=None),
        _make_key(id=k2, override=None),
    ]
    mock_placement_repo = AsyncMock()
    mock_placement_repo.map_active_backend_nodes_by_key.return_value = {
        k1: {pra_id, lv_id}, k2: {pra_id, lv_id},
    }
    mock_node_repo = AsyncMock()
    mock_node_repo.list_live_backends.return_value = [
        _make_node(id=pra_id, name="pra-backend-01"),
        _make_node(id=lv_id, name="rix-backend-01"),
    ]

    with patch(
        "services.vpn.keys.reconcilers.backend_rebalance.VpnKeyRepository",
        return_value=mock_key_repo,
    ), patch(
        "services.vpn.keys.reconcilers.backend_rebalance.UserPlacementRepository",
        return_value=mock_placement_repo,
    ), patch(
        "services.vpn.keys.reconcilers.backend_rebalance.VpnNodeRepository",
        return_value=mock_node_repo,
    ):
        await reconciler._tick()

    chosen = {call.args[0]: call.args[1]["entry_routing_override_backend_tag"]
              for call in mock_key_repo.update_by_id.await_args_list}
    # Both keys got distinct backends (one each)
    assert len(set(chosen.values())) == 2
