from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from services.vpn.keys.reconcilers.expiration import VpnKeyExpirationReconciler
from services.config import VpnKeyConfig


def _make_reconciler():
    cfg = VpnKeyConfig(expiration_enabled=True, expiration_tick_sec=60, expiration_batch_size=500)
    lock = MagicMock()
    lock.hold.return_value.__aenter__ = AsyncMock(return_value=True)
    lock.hold.return_value.__aexit__ = AsyncMock(return_value=False)
    return VpnKeyExpirationReconciler(vpn_key_settings=cfg, tick_lock=lock)


@pytest.mark.asyncio
async def test_no_expired_keys_returns_zero(async_session):
    reconciler = _make_reconciler()

    mock_key_repo = AsyncMock()
    mock_key_repo.bulk_revoke_expired.return_value = []

    with patch("services.vpn.keys.reconcilers.expiration.VpnKeyRepository", return_value=mock_key_repo), \
         patch("services.vpn.keys.reconcilers.expiration.UserPlacementRepository"), \
         patch("services.vpn.keys.reconcilers.expiration.NodeAgentPlacementTransport"):
        result = await reconciler._execute_tick()

    assert result == 0
    mock_key_repo.bulk_revoke_expired.assert_awaited_once_with(limit=500)


@pytest.mark.asyncio
async def test_expired_keys_bulk_revoked(async_session):
    reconciler = _make_reconciler()

    key_ids = [uuid4(), uuid4(), uuid4()]
    placement_ids = [uuid4(), uuid4()]

    mock_key_repo = AsyncMock()
    mock_key_repo.bulk_revoke_expired.return_value = key_ids

    mock_placement_repo = AsyncMock()
    mock_placement_repo.bulk_set_desired_state_for_keys.return_value = placement_ids

    mock_transport = AsyncMock()

    with patch("services.vpn.keys.reconcilers.expiration.VpnKeyRepository", return_value=mock_key_repo), \
         patch("services.vpn.keys.reconcilers.expiration.UserPlacementRepository", return_value=mock_placement_repo), \
         patch("services.vpn.keys.reconcilers.expiration.NodeAgentPlacementTransport", return_value=mock_transport):
        result = await reconciler._execute_tick()

    assert result == 3

    # Verify bulk placement update called once with all key_ids
    mock_placement_repo.bulk_set_desired_state_for_keys.assert_awaited_once()
    call_kwargs = mock_placement_repo.bulk_set_desired_state_for_keys.await_args.kwargs
    assert call_kwargs["key_ids"] == key_ids
    assert call_kwargs["desired_state"] == "inactive"
    assert call_kwargs["last_migration_reason"] == "key_expired"

    # Verify outbox enqueue called once with all placement_ids
    mock_transport.enqueue_for_placement_ids.assert_awaited_once_with(placement_ids)


@pytest.mark.asyncio
async def test_expired_keys_no_placements(async_session):
    reconciler = _make_reconciler()

    key_ids = [uuid4()]

    mock_key_repo = AsyncMock()
    mock_key_repo.bulk_revoke_expired.return_value = key_ids

    mock_placement_repo = AsyncMock()
    mock_placement_repo.bulk_set_desired_state_for_keys.return_value = []

    mock_transport = AsyncMock()

    with patch("services.vpn.keys.reconcilers.expiration.VpnKeyRepository", return_value=mock_key_repo), \
         patch("services.vpn.keys.reconcilers.expiration.UserPlacementRepository", return_value=mock_placement_repo), \
         patch("services.vpn.keys.reconcilers.expiration.NodeAgentPlacementTransport", return_value=mock_transport):
        result = await reconciler._execute_tick()

    assert result == 1
    mock_transport.enqueue_for_placement_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_returns_none():
    cfg = VpnKeyConfig(expiration_enabled=False)
    reconciler = VpnKeyExpirationReconciler(vpn_key_settings=cfg)
    result = await reconciler.run_once()
    assert result is None
