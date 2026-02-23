from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from services.vpn.subscriptions.service import SubscriptionService
from services.vpn.subscriptions.exceptions import (
    SubscriptionInactive,
    SubscriptionExpired,
    SubscriptionTokenExpired,
    SubscriptionBuild,
    SubscriptionRateLimited,
)
from services.vpn.subscriptions.constants import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SEC


@pytest.fixture()
def service(async_session, redis_client):
    svc = SubscriptionService(async_session, redis_client)
    svc.subscription_repository = AsyncMock()
    svc.node_repository = AsyncMock()
    svc.user_repository = AsyncMock()
    return svc


def _make_sub(
    *,
    is_active=True,
    expires_at=None,
    prev_token_hash=None,
    prev_token_expires_at=None,
    profile_key=None,
    preferred_region=None,
):
    sub = MagicMock()
    sub.id = uuid4()
    sub.client_id = uuid4()
    sub.is_active = is_active
    sub.expires_at = expires_at
    sub.prev_token_hash = prev_token_hash
    sub.prev_token_expires_at = prev_token_expires_at
    sub.profile_key = profile_key
    sub.preferred_region = preferred_region
    sub.token_hash = "current_hash"
    sub.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return sub


def _make_node(*, public_domain="vpn.example.com", name="node1", region="de"):
    n = MagicMock()
    n.public_domain = public_domain
    n.name = name
    n.region = region
    return n


def _make_transport_profile(*, network="tcp", security="reality", port=443):
    tp = MagicMock()
    tp.id = uuid4()
    tp.name = "reality-google"
    tp.network = network
    tp.security = security
    tp.reality_server_name = "www.google.com"
    tp.reality_public_key = "A" * 20
    tp.reality_short_id = "abcd1234"
    tp.tls_fingerprint = "chrome"
    tp.grpc_service_name = "vl"
    tp.flow = "xtls-rprx-vision"
    tp.port = port
    tp.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return tp


class TestValidateSubscription:
    def test_inactive_raises(self, service):
        sub = _make_sub(is_active=False)
        with pytest.raises(SubscriptionInactive):
            service._validate_subscription(sub, "hash")

    def test_expired_raises(self, service):
        sub = _make_sub(expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        with pytest.raises(SubscriptionExpired):
            service._validate_subscription(sub, "hash")

    def test_prev_token_expired_raises(self, service):
        sub = _make_sub(
            prev_token_hash="old_hash",
            prev_token_expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(SubscriptionTokenExpired):
            service._validate_subscription(sub, "old_hash")

    def test_prev_token_not_expired_ok(self, service):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        sub = _make_sub(
            prev_token_hash="old_hash",
            prev_token_expires_at=future,
        )
        # should not raise
        service._validate_subscription(sub, "old_hash")

    def test_active_valid_ok(self, service):
        future = datetime.now(timezone.utc) + timedelta(days=30)
        sub = _make_sub(expires_at=future)
        service._validate_subscription(sub, "hash")


class TestBuildRouteUri:
    def test_build_reality_uri(self, service):
        node = _make_node()
        transport_profile = _make_transport_profile(network="tcp", security="reality")

        uri = service._build_route_uri(
            client_id="cid",
            node=node,
            transport_profile=transport_profile,
        )

        assert uri is not None
        assert uri.startswith("vless://")

    def test_missing_domain_returns_none(self, service):
        node = _make_node(public_domain="")
        transport_profile = _make_transport_profile()
        service.settings.edge.public_domain = ""

        uri = service._build_route_uri(
            client_id="cid",
            node=node,
            transport_profile=transport_profile,
        )

        assert uri is None

    def test_build_grpc_tls_uri(self, service):
        node = _make_node()
        transport_profile = _make_transport_profile(network="grpc", security="tls")

        uri = service._build_route_uri(
            client_id="cid",
            node=node,
            transport_profile=transport_profile,
        )

        assert uri is not None
        assert "type=grpc" in uri
        assert "security=tls" in uri
        assert "serviceName=vl" in uri


class TestCalcEtag:
    def test_deterministic(self, service):
        sub = _make_sub()
        route_signatures = ["route-a|40", "route-b|30"]

        e1 = service._calc_etag(sub, route_signatures, client_id="cid", placement_op_version=3)
        e2 = service._calc_etag(sub, route_signatures, client_id="cid", placement_op_version=3)
        assert e1 == e2
        assert len(e1) == 64  # sha256 hex

    def test_route_order_changes_etag(self, service):
        sub = _make_sub()
        e1 = service._calc_etag(sub, ["route-a|40", "route-b|30"], client_id="cid")
        e2 = service._calc_etag(sub, ["route-b|30", "route-a|40"], client_id="cid")
        assert e1 != e2


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_first_request_sets_expire(self, async_session, redis_client):
        svc = SubscriptionService(async_session, redis_client)
        redis_client.client.incr.return_value = 1

        await svc._enforce_rate_limit("token_hash")

        redis_client.client.incr.assert_awaited_once_with("sub:rl:token_hash")
        redis_client.client.expire.assert_awaited_once_with(
            "sub:rl:token_hash",
            RATE_LIMIT_WINDOW_SEC,
        )

    @pytest.mark.asyncio
    async def test_request_over_limit_raises(self, async_session, redis_client):
        svc = SubscriptionService(async_session, redis_client)
        redis_client.client.incr.return_value = RATE_LIMIT_REQUESTS + 1

        with pytest.raises(SubscriptionRateLimited):
            await svc._enforce_rate_limit("token_hash")

        redis_client.client.expire.assert_not_awaited()
