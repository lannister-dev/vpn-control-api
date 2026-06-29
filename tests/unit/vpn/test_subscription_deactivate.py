from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.vpn.subscriptions.exceptions import SubscriptionNotFound
from services.vpn.subscriptions.service import SubscriptionService


def _subscription():
    sub = MagicMock()
    sub.id = uuid4()
    sub.expires_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
    return sub


@pytest.mark.asyncio
async def test_deactivate_not_found(async_session, redis_client):
    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    svc.vpn_key_repository.list_by_ids = AsyncMock(return_value=[])

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
    svc.node_agent_transport = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.list_key_ids_for_subscription.return_value = [device_key_id]

    device_key = MagicMock()
    device_key.id = device_key_id
    device_key.is_revoked = True
    svc.vpn_key_repository.list_by_ids = AsyncMock(return_value=[device_key])

    processed = await svc.deactivate(sub.id)

    assert processed == 1
    assert device_key.is_revoked is True
    assert svc.placement_repository.set_desired_state_for_key.await_count == 1
    assert svc.node_agent_transport.enqueue_for_key_state.await_count == 1
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
    svc.node_agent_transport = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.list_key_ids_for_subscription.return_value = [device_key_id]

    device_key = MagicMock()
    device_key.id = device_key_id
    device_key.is_revoked = False
    device_key.valid_until = None
    svc.vpn_key_repository.list_by_ids = AsyncMock(return_value=[device_key])

    restored = await svc.activate(sub.id)

    assert restored == 0
    assert device_key.is_revoked is False
    assert device_key.valid_until == sub.expires_at
    assert svc.placement_repository.set_desired_state_for_key.await_count == 1
    assert svc.node_agent_transport.enqueue_for_key_state.await_count == 1


@pytest.mark.asyncio
async def test_activate_ensures_backend_placements(async_session, redis_client):
    device_key_id = uuid4()
    sub = _subscription()

    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.node_agent_transport = AsyncMock()
    svc._ensure_backend_placements_for_key = AsyncMock(return_value=(uuid4(), MagicMock(), set()))
    svc._invalidate_payload_cache_by_token_hash = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.list_key_ids_for_subscription.return_value = [device_key_id]

    device_key = MagicMock()
    device_key.id = device_key_id
    device_key.is_revoked = True
    device_key.valid_until = None
    svc.vpn_key_repository.list_by_ids = AsyncMock(return_value=[device_key])

    restored = await svc.activate(sub.id)

    assert restored == 1
    assert device_key.is_revoked is False
    svc._ensure_backend_placements_for_key.assert_awaited_once()
    svc.placement_repository.set_desired_state_for_key.assert_not_awaited()
