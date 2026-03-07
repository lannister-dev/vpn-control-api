from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.vpn.subscriptions.exceptions import SubscriptionNotFound
from services.vpn.subscriptions.service import SubscriptionService


def _subscription():
    sub = MagicMock()
    sub.id = uuid4()
    return sub


@pytest.mark.asyncio
async def test_deactivate_not_found(async_session, redis_client):
    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = None

    with pytest.raises(SubscriptionNotFound):
        await svc.deactivate(uuid4())


@pytest.mark.asyncio
async def test_deactivate_revokes_device_keys(async_session, redis_client):
    device_key_id = uuid4()
    sub = _subscription()

    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.list_key_ids_for_subscription.return_value = [device_key_id]

    device_key = MagicMock()
    device_key.is_revoked = True

    async def _get_key_side_effect(key_id):
        if key_id == device_key_id:
            return device_key
        return None

    svc.vpn_key_repository.get_by_id.side_effect = _get_key_side_effect

    processed = await svc.deactivate(sub.id)

    assert processed == 1
    assert device_key.is_revoked is True
    assert svc.placement_repository.set_desired_state_for_key.await_count == 1
    svc.subscription_repository.update_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_restores_keys_and_placements(async_session, redis_client):
    device_key_id = uuid4()
    sub = _subscription()

    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.list_key_ids_for_subscription.return_value = [device_key_id]

    device_key = MagicMock()
    device_key.is_revoked = False

    async def _get_key_side_effect(key_id):
        if key_id == device_key_id:
            return device_key
        return None

    svc.vpn_key_repository.get_by_id.side_effect = _get_key_side_effect

    restored = await svc.activate(sub.id)

    assert restored == 0
    assert device_key.is_revoked is False
    assert svc.placement_repository.set_desired_state_for_key.await_count == 1
