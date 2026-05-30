from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.config import EntryRoutingConfig
from services.vpn.keys.reconcilers.backend_rebalance import BackendRebalanceReconciler


def _make_reconciler():
    cfg = EntryRoutingConfig(
        enabled=True,
        publisher_tick_sec=5,
        backend_rebalance_enabled=True,
        backend_rebalance_tick_sec=300,
        backend_rebalance_window_sec=300,
        backend_rebalance_ratio_threshold=3.0,
        backend_rebalance_min_bytes_per_sec=524288,
        backend_rebalance_cooldown_sec=1800,
        backend_rebalance_batch_size=1,
    )
    lock = MagicMock()
    lock.hold.return_value.__aenter__ = AsyncMock(return_value=True)
    lock.hold.return_value.__aexit__ = AsyncMock(return_value=False)
    return BackendRebalanceReconciler(routing_config=cfg, tick_lock=lock)


def _make_node(*, id, name, is_enabled=True, is_draining=False):
    return SimpleNamespace(id=id, name=name, is_enabled=is_enabled, is_draining=is_draining)


def _make_key(*, id, override=None):
    return SimpleNamespace(
        id=id,
        entry_routing_override_backend_tag=override,
        updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )


def _make_agg(*, node_id, bytes_in, bytes_out):
    return SimpleNamespace(
        node_id=node_id, bytes_in=bytes_in, bytes_out=bytes_out,
        total_sessions=0, active_sessions=0,
    )


@pytest.mark.asyncio
async def test_no_action_when_traffic_is_balanced(async_session):
    pra_id, lv_id = uuid4(), uuid4()
    reconciler = _make_reconciler()

    mock_node_repo = AsyncMock()
    mock_node_repo.list_live_backends.return_value = [
        _make_node(id=pra_id, name="pra-backend-01"),
        _make_node(id=lv_id, name="rix-backend-01"),
    ]
    mock_traffic_repo = AsyncMock()
    mock_traffic_repo.sum_backend_self.return_value = [
        _make_agg(node_id=pra_id, bytes_in=300 * 1024 * 1024, bytes_out=0),
        _make_agg(node_id=lv_id, bytes_in=200 * 1024 * 1024, bytes_out=0),
    ]

    with patch(
        "services.vpn.keys.backend_rebalance_service.VpnNodeRepository",
        return_value=mock_node_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.NodeTrafficUsageRepository",
        return_value=mock_traffic_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.VpnKeyRepository",
    ), patch(
        "services.vpn.keys.backend_rebalance_service.UserPlacementRepository",
    ):
        moved = await reconciler._service.run_once()

    assert moved == 0


@pytest.mark.asyncio
async def test_no_action_when_traffic_too_low(async_session):
    pra_id, lv_id = uuid4(), uuid4()
    reconciler = _make_reconciler()

    mock_node_repo = AsyncMock()
    mock_node_repo.list_live_backends.return_value = [
        _make_node(id=pra_id, name="pra-backend-01"),
        _make_node(id=lv_id, name="rix-backend-01"),
    ]
    mock_traffic_repo = AsyncMock()
    mock_traffic_repo.sum_backend_self.return_value = [
        _make_agg(node_id=pra_id, bytes_in=10_000, bytes_out=10_000),
        _make_agg(node_id=lv_id, bytes_in=0, bytes_out=0),
    ]

    with patch(
        "services.vpn.keys.backend_rebalance_service.VpnNodeRepository",
        return_value=mock_node_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.NodeTrafficUsageRepository",
        return_value=mock_traffic_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.VpnKeyRepository",
    ), patch(
        "services.vpn.keys.backend_rebalance_service.UserPlacementRepository",
    ):
        moved = await reconciler._service.run_once()

    assert moved == 0


@pytest.mark.asyncio
async def test_moves_one_key_when_traffic_imbalanced(async_session):
    pra_id, lv_id = uuid4(), uuid4()
    key_id = uuid4()
    reconciler = _make_reconciler()

    mock_node_repo = AsyncMock()
    mock_node_repo.list_live_backends.return_value = [
        _make_node(id=pra_id, name="pra-backend-01"),
        _make_node(id=lv_id, name="rix-backend-01"),
    ]
    mock_traffic_repo = AsyncMock()
    mock_traffic_repo.sum_backend_self.return_value = [
        _make_agg(node_id=pra_id, bytes_in=300 * 1024 * 1024, bytes_out=22 * 1024 * 1024),
        _make_agg(node_id=lv_id, bytes_in=3 * 1024 * 1024, bytes_out=0),
    ]
    mock_key_repo = AsyncMock()
    mock_key_repo.list_active_by_override_tag.return_value = [
        _make_key(id=key_id, override="backend-pra-backend-01"),
    ]
    mock_placement_repo = AsyncMock()
    mock_placement_repo.map_active_backend_nodes_by_key.return_value = {
        key_id: {pra_id, lv_id},
    }

    with patch(
        "services.vpn.keys.backend_rebalance_service.VpnNodeRepository",
        return_value=mock_node_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.NodeTrafficUsageRepository",
        return_value=mock_traffic_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.VpnKeyRepository",
        return_value=mock_key_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.UserPlacementRepository",
        return_value=mock_placement_repo,
    ):
        moved = await reconciler._service.run_once()

    assert moved == 1
    mock_key_repo.update_by_id.assert_awaited_once_with(
        key_id, {"entry_routing_override_backend_tag": "backend-rix-backend-01"},
    )


@pytest.mark.asyncio
async def test_skips_keys_without_dst_placement(async_session):
    pra_id, lv_id = uuid4(), uuid4()
    other_backend = uuid4()
    key_id = uuid4()
    reconciler = _make_reconciler()

    mock_node_repo = AsyncMock()
    mock_node_repo.list_live_backends.return_value = [
        _make_node(id=pra_id, name="pra-backend-01"),
        _make_node(id=lv_id, name="rix-backend-01"),
    ]
    mock_traffic_repo = AsyncMock()
    mock_traffic_repo.sum_backend_self.return_value = [
        _make_agg(node_id=pra_id, bytes_in=300 * 1024 * 1024, bytes_out=22 * 1024 * 1024),
        _make_agg(node_id=lv_id, bytes_in=0, bytes_out=0),
    ]
    mock_key_repo = AsyncMock()
    mock_key_repo.list_active_by_override_tag.return_value = [
        _make_key(id=key_id, override="backend-pra-backend-01"),
    ]
    mock_placement_repo = AsyncMock()
    mock_placement_repo.map_active_backend_nodes_by_key.return_value = {
        key_id: {pra_id, other_backend},
    }

    with patch(
        "services.vpn.keys.backend_rebalance_service.VpnNodeRepository",
        return_value=mock_node_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.NodeTrafficUsageRepository",
        return_value=mock_traffic_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.VpnKeyRepository",
        return_value=mock_key_repo,
    ), patch(
        "services.vpn.keys.backend_rebalance_service.UserPlacementRepository",
        return_value=mock_placement_repo,
    ):
        moved = await reconciler._service.run_once()

    assert moved == 0
    mock_key_repo.update_by_id.assert_not_awaited()
