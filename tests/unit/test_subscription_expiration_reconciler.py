from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.config import SubscriptionsExpirationConfig
from services.vpn.subscriptions.reconcilers.expiration import (
    SubscriptionExpirationReconciler,
    TickResult,
)


@pytest.fixture
def cfg():
    return SubscriptionsExpirationConfig(enabled=True, tick_sec=60, batch_size=50)


def _make_reconciler(cfg):
    lock = MagicMock()
    lock.hold = MagicMock()
    return SubscriptionExpirationReconciler(settings=cfg, tick_lock=lock)


async def test_disabled_returns_none():
    cfg = SubscriptionsExpirationConfig(enabled=False)
    rec = _make_reconciler(cfg)
    assert await rec.run_once() is None


async def test_execute_tick_no_expired_returns_zero(cfg):
    rec = _make_reconciler(cfg)

    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False
    rec._session_maker = MagicMock(return_value=fake_session)

    with patch(
        "services.vpn.subscriptions.reconcilers.expiration.SubscriptionRepository"
    ) as SubRepoCls, patch(
        "services.vpn.subscriptions.reconcilers.expiration.VpnKeyRepository"
    ), patch(
        "services.vpn.subscriptions.reconcilers.expiration.UserPlacementRepository"
    ), patch(
        "services.vpn.subscriptions.reconcilers.expiration.NodeAgentPlacementTransport"
    ):
        sub_repo = SubRepoCls.return_value
        sub_repo.list_expired_active = AsyncMock(return_value=[])
        result = await rec._execute_tick()

    assert result == TickResult(0, 0, 0)
    fake_session.commit.assert_not_awaited()


async def test_execute_tick_full_path_revokes_keys_and_deactivates(cfg):
    rec = _make_reconciler(cfg)

    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False
    rec._session_maker = MagicMock(return_value=fake_session)

    sub1 = SimpleNamespace(id=uuid4())
    sub2 = SimpleNamespace(id=uuid4())
    key_ids = [uuid4(), uuid4(), uuid4()]
    placement_ids = [uuid4(), uuid4()]

    with patch(
        "services.vpn.subscriptions.reconcilers.expiration.SubscriptionRepository"
    ) as SubRepoCls, patch(
        "services.vpn.subscriptions.reconcilers.expiration.VpnKeyRepository"
    ) as KeyRepoCls, patch(
        "services.vpn.subscriptions.reconcilers.expiration.UserPlacementRepository"
    ) as PlcRepoCls, patch(
        "services.vpn.subscriptions.reconcilers.expiration.NodeAgentPlacementTransport"
    ) as TransportCls:
        sub_repo = SubRepoCls.return_value
        sub_repo.list_expired_active = AsyncMock(return_value=[sub1, sub2])
        sub_repo.bulk_deactivate = AsyncMock(return_value=2)

        key_repo = KeyRepoCls.return_value
        key_repo.bulk_revoke_by_subscription_ids = AsyncMock(return_value=key_ids)

        plc_repo = PlcRepoCls.return_value
        plc_repo.bulk_set_desired_state_for_keys = AsyncMock(return_value=placement_ids)

        transport = TransportCls.return_value
        transport.enqueue_for_placement_ids = AsyncMock()

        result = await rec._execute_tick()

    assert result == TickResult(
        subscriptions_expired=2,
        keys_revoked=3,
        placements_affected=2,
    )
    sub_repo.bulk_deactivate.assert_awaited_once_with([sub1.id, sub2.id])
    transport.enqueue_for_placement_ids.assert_awaited_once_with(placement_ids)
    fake_session.commit.assert_awaited_once()


async def test_execute_tick_subs_without_keys_still_deactivates(cfg):
    rec = _make_reconciler(cfg)

    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False
    rec._session_maker = MagicMock(return_value=fake_session)

    sub1 = SimpleNamespace(id=uuid4())

    with patch(
        "services.vpn.subscriptions.reconcilers.expiration.SubscriptionRepository"
    ) as SubRepoCls, patch(
        "services.vpn.subscriptions.reconcilers.expiration.VpnKeyRepository"
    ) as KeyRepoCls, patch(
        "services.vpn.subscriptions.reconcilers.expiration.UserPlacementRepository"
    ) as PlcRepoCls, patch(
        "services.vpn.subscriptions.reconcilers.expiration.NodeAgentPlacementTransport"
    ) as TransportCls:
        sub_repo = SubRepoCls.return_value
        sub_repo.list_expired_active = AsyncMock(return_value=[sub1])
        sub_repo.bulk_deactivate = AsyncMock(return_value=1)

        key_repo = KeyRepoCls.return_value
        key_repo.bulk_revoke_by_subscription_ids = AsyncMock(return_value=[])

        plc_repo = PlcRepoCls.return_value
        plc_repo.bulk_set_desired_state_for_keys = AsyncMock()

        transport = TransportCls.return_value
        transport.enqueue_for_placement_ids = AsyncMock()

        result = await rec._execute_tick()

    assert result.subscriptions_expired == 1
    assert result.keys_revoked == 0
    assert result.placements_affected == 0
    plc_repo.bulk_set_desired_state_for_keys.assert_not_awaited()
    transport.enqueue_for_placement_ids.assert_not_awaited()
    sub_repo.bulk_deactivate.assert_awaited_once()
    fake_session.commit.assert_awaited_once()
