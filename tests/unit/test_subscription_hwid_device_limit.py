from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.vpn.subscriptions.exceptions import SubscriptionHwidRequired, SubscriptionDeviceLimitReached
from services.vpn.subscriptions.service import SubscriptionService


@pytest.fixture()
def service(async_session, redis_client, monkeypatch):
    # Force default require_hwid to True for these tests.
    from services import config as cfg

    settings = cfg.get_settings()
    settings.subscriptions.require_hwid_default = True
    settings.subscriptions.max_devices_default = 1
    monkeypatch.setattr(cfg, "get_settings", lambda: settings)

    svc = SubscriptionService(async_session, redis_client)
    svc.redis.client.incr = AsyncMock(return_value=1)
    svc.redis.client.expire = AsyncMock(return_value=True)
    svc.subscription_repository = AsyncMock()
    svc.device_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.routing_service = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.route_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    return svc


def _sub(*, hwid_enabled=True, max_devices=None):
    s = MagicMock()
    s.id = uuid4()
    s.user_id = uuid4()
    s.client_id = uuid4()
    s.root_vpn_key_id = None
    s.is_active = True
    s.expires_at = None
    s.prev_token_hash = None
    s.prev_token_expires_at = None
    s.profile_key = "ws_tls_v1"
    s.preferred_region = None
    s.token_hash = "h"
    s.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    s.hwid_enabled = hwid_enabled
    s.max_devices = max_devices
    return s


@pytest.mark.asyncio
async def test_missing_hwid_raises(service):
    service.subscription_repository.get_by_any_token_hash.return_value = _sub(hwid_enabled=True)
    with pytest.raises(SubscriptionHwidRequired):
        await service.build_payload(raw_token="tok", hwid=None, user_agent=None)


@pytest.mark.asyncio
async def test_device_limit_reached(service):
    sub = _sub(hwid_enabled=True, max_devices=1)
    service.subscription_repository.get_by_any_token_hash.return_value = sub
    service.device_repository.get_active_by_sub_and_hwid_hash.return_value = None
    service.device_repository.count_active_for_subscription.return_value = 1
    with pytest.raises(SubscriptionDeviceLimitReached):
        await service.build_payload(raw_token="tok", hwid="device1", user_agent="ua")
    service.session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_hwid_path_skips_subscription_lock(service):
    sub = _sub(hwid_enabled=True, max_devices=1)
    device = MagicMock()
    device.id = uuid4()
    device.vpn_key_id = uuid4()
    key = MagicMock()
    key.client_id = str(uuid4())
    key.id = device.vpn_key_id
    key.is_revoked = False

    service.subscription_repository.get_by_any_token_hash.return_value = sub
    service.device_repository.get_active_by_sub_and_hwid_hash.return_value = device
    service.vpn_key_repository.get_by_id.return_value = key
    service._enforce_rate_limit = AsyncMock()
    placement = MagicMock()
    placement.op_version = 4
    preferred_backend_id = uuid4()
    service._ensure_backend_placements_for_key = AsyncMock(
        return_value=(preferred_backend_id, placement, {preferred_backend_id})
    )
    route = MagicMock()
    route.id = uuid4()
    route.health_status = "healthy"
    route.effective_weight = 50
    node = MagicMock()
    node.id = preferred_backend_id
    node.name = "be-fi-1"
    node.region = "fi"
    node.public_domain = "be-fi-1.example.com"
    tp = MagicMock()
    tp.id = uuid4()
    tp.port = 443
    tp.security = "reality"
    tp.network = "tcp"
    service.route_repository.list_resolved_active = AsyncMock(return_value=[(route, node, tp)])
    service._build_route_uri = MagicMock(return_value="vless://ok")
    service._route_signature = MagicMock(return_value="route-signature")
    service._calc_etag = MagicMock(return_value="etag")

    await service.build_payload(raw_token="tok", hwid="device1", user_agent="ua")

    service.session.execute.assert_not_awaited()


