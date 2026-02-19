from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.vpn.subscriptions.exceptions import SubscriptionNotFound
from services.vpn.subscriptions.service import SubscriptionService


def _subscription():
    sub = MagicMock()
    sub.id = uuid4()
    return sub


def _device(subscription_id):
    d = MagicMock()
    d.id = uuid4()
    d.subscription_id = subscription_id
    d.vpn_key_id = uuid4()
    d.hwid_hash = "a" * 64
    d.last_seen_at = datetime.now(timezone.utc)
    d.user_agent = "happ/1.0"
    d.is_active = True
    d.created_at = datetime.now(timezone.utc)
    d.updated_at = datetime.now(timezone.utc)
    return d


@pytest.mark.asyncio
async def test_list_devices_not_found(async_session, redis_client):
    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = None

    with pytest.raises(SubscriptionNotFound):
        await svc.list_devices(uuid4())


@pytest.mark.asyncio
async def test_list_devices_success(async_session, redis_client):
    sub = _subscription()
    dev = _device(sub.id)

    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.list_by_subscription.return_value = [dev]

    out = await svc.list_devices(sub.id, active_only=True)

    assert len(out) == 1
    assert out[0].id == dev.id
    svc.device_repository.list_by_subscription.assert_awaited_once_with(sub.id, active_only=True)


@pytest.mark.asyncio
async def test_revoke_device_not_found(async_session, redis_client):
    sub = _subscription()

    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.get_by_id_for_subscription.return_value = None

    with pytest.raises(HTTPException) as exc:
        await svc.revoke_device(sub.id, uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_revoke_device_success(async_session, redis_client):
    sub = _subscription()
    dev = _device(sub.id)

    key = MagicMock()
    key.id = dev.vpn_key_id
    key.is_revoked = False

    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.get_by_id_for_subscription.return_value = dev
    svc.vpn_key_repository.get_by_id.return_value = key
    placement = MagicMock()
    placement.backend_node_id = uuid4()
    placement.gateway_node_id = uuid4()
    placement.sticky_until = None
    svc.placement_repository.get_by_key_id.return_value = placement

    changed = await svc.revoke_device(sub.id, dev.id)

    assert changed is True
    assert key.is_revoked is True
    svc.device_repository.update_by_id.assert_awaited_once()
    svc.placement_repository.upsert_set_pending.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_device_idempotent(async_session, redis_client):
    sub = _subscription()
    dev = _device(sub.id)
    dev.is_active = False

    key = MagicMock()
    key.id = dev.vpn_key_id
    key.is_revoked = True

    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.placement_repository = AsyncMock()

    svc.subscription_repository.get_by_id.return_value = sub
    svc.device_repository.get_by_id_for_subscription.return_value = dev
    svc.vpn_key_repository.get_by_id.return_value = key
    placement = MagicMock()
    placement.backend_node_id = uuid4()
    placement.gateway_node_id = uuid4()
    placement.sticky_until = None
    svc.placement_repository.get_by_key_id.return_value = placement

    changed = await svc.revoke_device(sub.id, dev.id)

    assert changed is False
    svc.device_repository.update_by_id.assert_not_awaited()
    svc.placement_repository.upsert_set_pending.assert_awaited_once()
