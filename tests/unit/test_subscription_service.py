from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from services.vpn.subscriptions.service import SubscriptionService
from services.vpn.subscriptions.exceptions import (
    SubscriptionInactive,
    SubscriptionExpired,
    SubscriptionTokenExpired,
    SubscriptionBuild,
    SubscriptionNotFound,
    SubscriptionRateLimited,
)
from services.vpn.subscriptions.constants import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SEC
from services.vpn.subscriptions.schemas import ResolvedSubscriptionRoute, SubscriptionCreateIn
from shared.profiles.types import ProfileType


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

    @pytest.mark.asyncio
    async def test_invalidate_payload_cache_uses_index_and_deletes_keys(self, async_session, redis_client):
        svc = SubscriptionService(async_session, redis_client)
        redis_client.client.smembers.return_value = {
            "sub:cfg:hash:a",
            "sub:cfg:hash:b",
            "not:sub:key",
        }

        await svc._invalidate_payload_cache_by_token_hash("hash")

        redis_client.client.smembers.assert_awaited_once_with("sub:cfg:index:hash")
        first_delete_call = redis_client.client.delete.await_args_list[0]
        assert set(first_delete_call.args) == {"sub:cfg:hash:a", "sub:cfg:hash:b"}
        redis_client.client.delete.assert_any_await("sub:cfg:index:hash")

    @pytest.mark.asyncio
    async def test_write_payload_cache_updates_index(self, async_session, redis_client):
        svc = SubscriptionService(async_session, redis_client)

        ok = await svc._write_payload_cache(
            token_hash="hash",
            cache_key="sub:cfg:hash:none",
            payload="vless://cached",
            etag="etag",
            ttl_sec=15,
        )

        assert ok
        redis_client.client.setex.assert_awaited_once()
        redis_client.client.sadd.assert_awaited_once_with(
            "sub:cfg:index:hash",
            "sub:cfg:hash:none",
        )
        redis_client.client.expire.assert_awaited_once_with("sub:cfg:index:hash", 75)


@pytest.mark.asyncio
async def test_build_payload_uses_cached_payload_without_db_lookup(service):
    service.settings.subscriptions.response_cache_ttl_sec = 15
    service._enforce_rate_limit = AsyncMock()
    service.redis.client.get.return_value = json.dumps(
        {"etag": "etag-cached", "payload": "vless://cached"}
    )

    payload, etag, not_modified = await service.build_payload(raw_token="tok")

    assert payload == "vless://cached"
    assert etag == "etag-cached"
    assert not not_modified
    service.subscription_repository.get_by_any_token_hash.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_payload_uses_cached_etag_for_304_without_db_lookup(service):
    service.settings.subscriptions.response_cache_ttl_sec = 15
    service._enforce_rate_limit = AsyncMock()
    service.redis.client.get.return_value = json.dumps(
        {"etag": "etag-cached", "payload": "vless://cached"}
    )

    payload, etag, not_modified = await service.build_payload(
        raw_token="tok",
        if_none_match="etag-cached",
    )

    assert payload == ""
    assert etag == "etag-cached"
    assert not_modified
    service.subscription_repository.get_by_any_token_hash.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_payload_waits_on_lock_contention_and_uses_wait_hit_cache(service):
    service.settings.subscriptions.response_cache_ttl_sec = 15
    service._enforce_rate_limit = AsyncMock()
    service.redis.client.get.side_effect = [
        None,
        json.dumps({"etag": "etag-wait", "payload": "vless://waited"}),
    ]
    service.redis.client.set.return_value = None

    with patch("services.vpn.subscriptions.service.asyncio.sleep", new=AsyncMock()):
        payload, etag, not_modified = await service.build_payload(raw_token="tok")

    assert payload == "vless://waited"
    assert etag == "etag-wait"
    assert not not_modified
    service.subscription_repository.get_by_any_token_hash.assert_not_awaited()
    service.redis.client.set.assert_awaited()


@pytest.mark.asyncio
async def test_build_payload_releases_lock_when_build_fails(service):
    service.settings.subscriptions.response_cache_ttl_sec = 15
    service._enforce_rate_limit = AsyncMock()
    service.redis.client.get.return_value = None
    service.redis.client.set.return_value = True
    service.subscription_repository.get_by_any_token_hash.return_value = None

    with pytest.raises(SubscriptionNotFound):
        await service.build_payload(raw_token="tok")

    first_delete_call = service.redis.client.delete.await_args_list[0]
    assert len(first_delete_call.args) == 1
    assert str(first_delete_call.args[0]).startswith("sub:cfg:lock:")


def test_route_selector_limits_size_and_keeps_fallback_diversity(service):
    preferred_backend = uuid4()
    fallback_backend_1 = uuid4()
    fallback_backend_2 = uuid4()

    service.settings.subscriptions.smart_route_max_count = 4
    routes = [
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=preferred_backend,
            transport_security="reality",
            transport_network="tcp",
            uri="vless://p1",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=preferred_backend,
            transport_security="reality",
            transport_network="tcp",
            uri="vless://p2",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=fallback_backend_1,
            transport_security="reality",
            transport_network="tcp",
            uri="vless://f1",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=fallback_backend_1,
            transport_security="reality",
            transport_network="tcp",
            uri="vless://f1b",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=fallback_backend_2,
            transport_security="tls",
            transport_network="grpc",
            uri="vless://f2",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
    ]

    out = service.route_selector.select(
        routes=routes,
        preferred_backend_id=preferred_backend,
        max_routes=service.settings.subscriptions.smart_route_max_count,
    )

    assert len(out) == 4
    assert out[0].backend_node_id == preferred_backend
    assert out[1].backend_node_id == preferred_backend
    assert out[2].backend_node_id == fallback_backend_1
    assert out[3].backend_node_id == fallback_backend_2


@pytest.mark.asyncio
async def test_create_subscription_includes_subscription_url_when_base_url_set(service):
    user_id = uuid4()
    service.settings.subscriptions.public_base_url = "https://api.example.com/subscriptions/sub/"
    service.user_repository.get_by_id = AsyncMock(return_value=MagicMock())
    sub = MagicMock()
    sub.id = uuid4()
    sub.client_id = uuid4()
    sub.hwid_enabled = False
    sub.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    sub.is_active = True
    service.subscription_repository.create = AsyncMock(return_value=sub)
    key = MagicMock()
    key.id = uuid4()
    service.vpn_key_repository.create = AsyncMock(return_value=key)

    with patch("services.vpn.subscriptions.service.ProfileRegistry.get") as get_profile:
        get_profile.return_value = SimpleNamespace(
            profile=SimpleNamespace(type=ProfileType.reality_tcp)
        )
        out = await service.create(
            SubscriptionCreateIn(
                user_id=user_id,
                profile_key="default-reality",
            )
        )

    assert out.subscription_url.startswith("https://api.example.com/subscriptions/sub/")


@pytest.mark.asyncio
async def test_create_subscription_url_uses_base_url_as_is(service):
    user_id = uuid4()
    service.settings.subscriptions.public_base_url = "https://api.example.com/custom-prefix/"
    service.user_repository.get_by_id = AsyncMock(return_value=MagicMock())
    sub = MagicMock()
    sub.id = uuid4()
    sub.client_id = uuid4()
    sub.hwid_enabled = False
    sub.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    sub.is_active = True
    service.subscription_repository.create = AsyncMock(return_value=sub)
    key = MagicMock()
    key.id = uuid4()
    service.vpn_key_repository.create = AsyncMock(return_value=key)

    with patch("services.vpn.subscriptions.service.ProfileRegistry.get") as get_profile:
        get_profile.return_value = SimpleNamespace(
            profile=SimpleNamespace(type=ProfileType.reality_tcp)
        )
        out = await service.create(
            SubscriptionCreateIn(
                user_id=user_id,
                profile_key="default-reality",
            )
        )

    assert out.subscription_url.startswith("https://api.example.com/custom-prefix/")


def test_fit_routes_to_payload_limit_keeps_all_when_within_limit(service):
    routes = [
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=uuid4(),
            transport_security="reality",
            transport_network="tcp",
            uri="vless://a",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=uuid4(),
            transport_security="tls",
            transport_network="grpc",
            uri="vless://b",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
    ]
    selected, result = service._fit_routes_to_payload_limit(
        routes=routes,
        max_payload_bytes=1024,
    )

    assert result == "ok"
    assert selected == routes


def test_fit_routes_to_payload_limit_trims_when_needed(service):
    routes = [
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=uuid4(),
            transport_security="reality",
            transport_network="tcp",
            uri="vless://12345",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=uuid4(),
            transport_security="tls",
            transport_network="grpc",
            uri="vless://67890",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
    ]
    selected, result = service._fit_routes_to_payload_limit(
        routes=routes,
        max_payload_bytes=len("vless://12345"),
    )

    assert result == "trimmed"
    assert selected == [routes[0]]


def test_fit_routes_to_payload_limit_rejects_if_single_route_too_large(service):
    routes = [
        ResolvedSubscriptionRoute(
            route_id=uuid4(),
            backend_node_id=uuid4(),
            transport_security="reality",
            transport_network="tcp",
            uri="vless://this-is-too-long",
            route=MagicMock(),
            node=MagicMock(),
            transport_profile=MagicMock(),
        ),
    ]
    selected, result = service._fit_routes_to_payload_limit(
        routes=routes,
        max_payload_bytes=8,
    )

    assert result == "rejected"
    assert selected == []
