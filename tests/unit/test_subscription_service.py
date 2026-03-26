from __future__ import annotations

import json
import pytest
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from fastapi import HTTPException

from services.vpn.subscriptions import redis_key
from services.vpn.subscriptions.schemas import (
    ResolvedDeviceBundle,
    ResolvedDeviceKey,
    TransportBuildResult,
)
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
    svc.device_repository = AsyncMock()
    svc.device_key_repository = AsyncMock()
    svc.vpn_key_repository = AsyncMock()
    svc.device_key_repository.list_by_device_ids = AsyncMock(return_value=[])
    svc.vpn_key_repository.list_by_ids = AsyncMock(return_value=[])
    svc.routing_service = AsyncMock()
    svc.placement_repository = AsyncMock()
    svc.route_repository = AsyncMock()
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


def _make_node(*, public_domain="vpn.example.com", reality_ip=None, name="node1", region="de"):
    n = MagicMock()
    n.public_domain = public_domain
    n.reality_ip = public_domain if reality_ip is None else reality_ip
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


def _make_bundle(*transports: str):
    device = MagicMock()
    device.id = uuid4()
    keys = []
    for idx, transport in enumerate(transports):
        key = MagicMock()
        key.id = uuid4()
        key.transport = transport
        key.client_id = f"client-{transport}"
        keys.append(
            ResolvedDeviceKey(
                vpn_key_id=key.id,
                transport=transport,
                client_id=key.client_id,
                is_primary=idx == 0,
                key=key,
            )
        )
    return ResolvedDeviceBundle(device=device, keys=tuple(keys))


def _make_subscription_row(*, user_id=None, is_active=True):
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    sub = MagicMock()
    sub.id = uuid4()
    sub.user_id = user_id or uuid4()
    sub.client_id = uuid4()
    sub.root_vpn_key_id = None
    sub.plan_id = None
    sub.plan = None
    sub.is_active = is_active
    sub.expires_at = now + timedelta(days=30)
    sub.profile_key = "ws_tls_v1"
    sub.preferred_region = "fi"
    sub.hwid_enabled = True
    sub.max_devices = 2
    sub.used_traffic_bytes = 0
    sub.lifetime_used_traffic_bytes = 0
    sub.last_traffic_reset_at = None
    sub.created_at = now
    sub.updated_at = now
    return sub


@pytest.mark.asyncio
async def test_get_subscription_returns_out(service):
    sub = _make_subscription_row()
    service.subscription_repository.get_by_id.return_value = sub

    out = await service.get_subscription(sub.id)

    assert out.id == sub.id
    assert out.user_id == sub.user_id
    assert out.profile_key == "ws_tls_v1"
    assert out.hwid_enabled is True


@pytest.mark.asyncio
async def test_get_subscription_not_found_raises(service):
    service.subscription_repository.get_by_id.return_value = None

    with pytest.raises(SubscriptionNotFound):
        await service.get_subscription(uuid4())


@pytest.mark.asyncio
async def test_list_subscriptions_by_user(service):
    user_id = uuid4()
    rows = [_make_subscription_row(user_id=user_id), _make_subscription_row(user_id=user_id)]
    service.subscription_repository.list_by_user_id.return_value = rows

    out = await service.list_subscriptions_by_user(user_id=user_id, active_only=True)

    assert len(out) == 2
    assert {item.user_id for item in out} == {user_id}
    service.subscription_repository.list_by_user_id.assert_awaited_once_with(
        user_id=user_id,
        active_only=True,
    )


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

    def test_build_reality_uri_uses_node_host_even_with_global_edge_domain(self, service):
        node = _make_node(public_domain="1.2.3.4")
        transport_profile = _make_transport_profile(network="tcp", security="reality")
        service.settings.edge.public_domain = "prod.example.com"

        uri = service._build_route_uri(
            client_id="cid",
            node=node,
            transport_profile=transport_profile,
        )

        assert uri is not None
        assert "@1.2.3.4:" in uri
        assert "prod.example.com" not in uri

    def test_build_reality_uri_prefers_reality_ip(self, service):
        node = _make_node(public_domain="reality.example.com", reality_ip="198.51.100.12")
        transport_profile = _make_transport_profile(network="tcp", security="reality")
        service.settings.edge.public_domain = "prod.example.com"

        uri = service._build_route_uri(
            client_id="cid",
            node=node,
            transport_profile=transport_profile,
        )

        assert uri is not None
        assert "@198.51.100.12:" in uri
        assert "reality.example.com" not in uri

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

    def test_bundle_client_signature_changes_etag_when_transport_changes(self, service):
        sub = _make_sub()
        e1 = service._calc_etag(
            sub,
            ["reality-route|40", "ws-route|30"],
            client_id="reality:cid-a,ws:cid-b",
            placement_op_version="reality:7,ws:9",
        )
        e2 = service._calc_etag(
            sub,
            ["reality-route|40", "ws-route|31"],
            client_id="reality:cid-a,ws:cid-b",
            placement_op_version="reality:7,ws:9",
        )
        assert e1 != e2


def test_transport_label_normalizes_enum_like_string(service):
    assert service._transport_label("VpnTransport.reality") == "Reality"
    assert service._transport_label("TransportVpnTransport.ws") == "WS"


def test_route_transport_compatibility(service):
    assert service._is_route_compatible_with_key_transport(
        key_transport="reality",
        transport_security="reality",
        transport_network="tcp",
    )
    assert not service._is_route_compatible_with_key_transport(
        key_transport="reality",
        transport_security="tls",
        transport_network="ws",
    )
    assert not service._is_route_compatible_with_key_transport(
        key_transport="tcp",
        transport_security="reality",
        transport_network="tcp",
    )
    assert not service._is_route_compatible_with_key_transport(
        key_transport="tcp",
        transport_security="tls",
        transport_network="ws",
    )
    assert service._is_route_compatible_with_key_transport(
        key_transport="ws",
        transport_security="tls",
        transport_network="ws",
    )
    assert not service._is_route_compatible_with_key_transport(
        key_transport="ws",
        transport_security="reality",
        transport_network="tcp",
    )


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_first_request_sets_expire(self, async_session, redis_client):
        svc = SubscriptionService(async_session, redis_client)
        redis_client.client.incr.return_value = 1
        rate_limit_key = redis_key.rate_limit("token_hash")

        await svc._enforce_rate_limit("token_hash")

        redis_client.client.incr.assert_awaited_once_with(rate_limit_key)
        redis_client.client.expire.assert_awaited_once_with(
            rate_limit_key,
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
        token_hash = "hash"
        first_payload_key = redis_key.payload_cache(token_hash=token_hash, hwid="a")
        second_payload_key = redis_key.payload_cache(token_hash=token_hash, hwid="b")
        index_key = redis_key.payload_cache_index(token_hash=token_hash)
        redis_client.client.smembers.return_value = {
            first_payload_key,
            second_payload_key,
            "not:sub:key",
        }

        await svc._invalidate_payload_cache_by_token_hash(token_hash)

        redis_client.client.smembers.assert_awaited_once_with(index_key)
        first_delete_call = redis_client.client.delete.await_args_list[0]
        assert set(first_delete_call.args) == {first_payload_key, second_payload_key}
        redis_client.client.delete.assert_any_await(index_key)

    @pytest.mark.asyncio
    async def test_write_payload_cache_updates_index(self, async_session, redis_client):
        svc = SubscriptionService(async_session, redis_client)
        token_hash = "hash"
        cache_key = redis_key.payload_cache(token_hash=token_hash, hwid=None)
        index_key = redis_key.payload_cache_index(token_hash=token_hash)

        ok = await svc._write_payload_cache(
            token_hash=token_hash,
            cache_key=cache_key,
            payload="vless://cached",
            etag="etag",
            ttl_sec=15,
        )

        assert ok
        redis_client.client.setex.assert_awaited_once()
        redis_client.client.sadd.assert_awaited_once_with(
            index_key,
            cache_key,
        )
        redis_client.client.expire.assert_awaited_once_with(index_key, 75)


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
    lock_prefix = redis_key.payload_build_lock(token_hash="", hwid=None).split("::", 1)[0] + ":"
    assert str(first_delete_call.args[0]).startswith(lock_prefix)


@pytest.mark.asyncio
async def test_build_payload_fetches_route_buffer_scaled_to_max_routes(service):
    preferred_backend_id = uuid4()
    service.settings.subscriptions.response_cache_ttl_sec = 0
    service.settings.subscriptions.smart_route_max_count = 6
    service._enforce_rate_limit = AsyncMock()
    service._resolve_device_bundle_for_request = AsyncMock(return_value=_make_bundle("reality"))
    service._ensure_backend_placements_for_key = AsyncMock(
        return_value=(preferred_backend_id, MagicMock(op_version=7), {preferred_backend_id})
    )
    service._build_route_uri = MagicMock(return_value=None)
    service.subscription_repository.get_by_any_token_hash.return_value = _make_sub(
        profile_key="reality_tcp_v1",
        preferred_region="fr",
    )
    service.route_repository = AsyncMock()
    service.route_repository.list_resolved_active = AsyncMock(return_value=[])

    with pytest.raises(SubscriptionBuild) as exc:
        await service.build_payload(raw_token="tok")

    assert str(exc.value).startswith("No available routes")
    assert service.route_repository.list_resolved_active.await_count == 2
    first_call = service.route_repository.list_resolved_active.await_args_list[0]
    assert first_call.kwargs["preferred_node_id"] == preferred_backend_id
    assert first_call.kwargs["preferred_region"] == "fr"
    assert first_call.kwargs["limit"] == 24
    assert first_call.kwargs["backend_node_ids"] == [preferred_backend_id]


@pytest.mark.asyncio
async def test_build_payload_merges_multiple_transports(service):
    service.settings.subscriptions.response_cache_ttl_sec = 0
    service._enforce_rate_limit = AsyncMock()
    sub = _make_sub(profile_key="ws_tls_v1", preferred_region="fr")
    service.subscription_repository.get_by_any_token_hash.return_value = sub
    service._resolve_device_bundle_for_request = AsyncMock(
        return_value=_make_bundle("reality", "ws")
    )

    france_node = _make_node(public_domain="fr.example.com", reality_ip="198.51.100.10", region="fr")
    france_node.id = uuid4()
    finland_node = _make_node(public_domain="fi.example.com", reality_ip="198.51.100.20", region="fi")
    finland_node.id = uuid4()
    route = MagicMock()
    route.id = uuid4()
    route.health_status = "healthy"
    route.effective_weight = 100
    tp_reality = _make_transport_profile(network="tcp", security="reality")
    tp_ws = _make_transport_profile(network="ws", security="tls")

    async def _build_transport(*, subscription, key, max_routes):
        if key.transport == "reality":
            return TransportBuildResult(
                key=key,
                routes=(
                    ResolvedSubscriptionRoute(
                        route_id=uuid4(),
                        backend_node_id=france_node.id,
                        vpn_key_id=key.vpn_key_id,
                        vpn_transport=key.transport,
                        client_id=key.client_id,
                        transport_security="reality",
                        transport_network="tcp",
                        country_code="FR",
                        country_name="France",
                        display_name="France Reality",
                        preferred_backend=True,
                        selection_rank=0,
                        uri="vless://fr-reality#France%20Reality",
                        route=route,
                        node=france_node,
                        transport_profile=tp_reality,
                    ),
                ),
                placement_signature="reality:7",
                diagnostic_reason=None,
            )
        return TransportBuildResult(
            key=key,
            routes=(
                ResolvedSubscriptionRoute(
                    route_id=uuid4(),
                    backend_node_id=france_node.id,
                    vpn_key_id=key.vpn_key_id,
                    vpn_transport=key.transport,
                    client_id=key.client_id,
                    transport_security="tls",
                    transport_network="ws",
                    country_code="FR",
                    country_name="France",
                    display_name="France WS",
                    preferred_backend=True,
                    selection_rank=0,
                    uri="vless://fr-ws#France%20WS",
                    route=route,
                    node=france_node,
                    transport_profile=tp_ws,
                ),
                ResolvedSubscriptionRoute(
                    route_id=uuid4(),
                    backend_node_id=finland_node.id,
                    vpn_key_id=key.vpn_key_id,
                    vpn_transport=key.transport,
                    client_id=key.client_id,
                    transport_security="tls",
                    transport_network="ws",
                    country_code="FI",
                    country_name="Finland",
                    display_name="Finland WS",
                    preferred_backend=False,
                    selection_rank=1,
                    uri="vless://fi-ws#Finland%20WS",
                    route=route,
                    node=finland_node,
                    transport_profile=tp_ws,
                ),
            ),
            placement_signature="ws:9",
            diagnostic_reason=None,
        )

    service._build_transport_routes = AsyncMock(side_effect=_build_transport)

    payload, etag, not_modified = await service.build_payload(raw_token="tok", hwid="hwid-1")

    lines = payload.splitlines()
    assert len(lines) == 3
    # France has 2 routes (reality + ws) → numbered
    assert "fr-reality" in lines[0]
    assert "France%201" in lines[0]
    assert "fr-ws" in lines[1]
    assert "France%202" in lines[1]
    # Finland has 1 route → no number
    assert "fi-ws" in lines[2]
    assert "Finland" in lines[2]
    assert etag
    assert not not_modified


@pytest.mark.asyncio
async def test_build_payload_keeps_available_transport_when_second_pending(service):
    service.settings.subscriptions.response_cache_ttl_sec = 0
    service._enforce_rate_limit = AsyncMock()
    service.subscription_repository.get_by_any_token_hash.return_value = _make_sub(
        profile_key="ws_tls_v1",
        preferred_region="fr",
    )
    service._resolve_device_bundle_for_request = AsyncMock(
        return_value=_make_bundle("reality", "ws")
    )

    route = MagicMock()
    route.id = uuid4()
    route.health_status = "healthy"
    route.effective_weight = 100
    node = _make_node(public_domain="fr.example.com", reality_ip="198.51.100.10", region="fr")
    node.id = uuid4()
    tp = _make_transport_profile(network="tcp", security="reality")

    async def _build_transport(*, subscription, key, max_routes):
        if key.transport == "ws":
            return TransportBuildResult(
                key=key,
                routes=(),
                placement_signature=None,
                diagnostic_reason="transport_pending",
            )
        return TransportBuildResult(
            key=key,
            routes=(
                ResolvedSubscriptionRoute(
                    route_id=uuid4(),
                    backend_node_id=node.id,
                    vpn_key_id=key.vpn_key_id,
                    vpn_transport=key.transport,
                    client_id=key.client_id,
                    transport_security="reality",
                    transport_network="tcp",
                    country_code="FR",
                    country_name="France",
                    display_name="France Reality",
                    preferred_backend=True,
                    selection_rank=0,
                    uri="vless://fr-reality#France%20Reality",
                    route=route,
                    node=node,
                    transport_profile=tp,
                ),
            ),
            placement_signature="reality:4",
            diagnostic_reason=None,
        )

    service._build_transport_routes = AsyncMock(side_effect=_build_transport)

    payload, _, _ = await service.build_payload(raw_token="tok", hwid="hwid-1")

    assert payload == "vless://fr-reality#France%20Reality"


@pytest.mark.asyncio
async def test_load_device_bundle_returns_empty_without_bindings(service):
    device = MagicMock()
    device.id = uuid4()
    service.device_key_repository.list_by_device_ids.return_value = []
    service.vpn_key_repository.list_by_ids.return_value = []

    bundle = await service._load_device_bundle(device)

    assert bundle.keys == ()


def test_merge_transport_routes_numbers_same_country_backends(service):
    route = MagicMock()
    route.id = uuid4()
    route.effective_weight = 50
    node = _make_node(public_domain="fr.example.com", reality_ip="198.51.100.10", region="fr")
    node.id = uuid4()
    node_2 = _make_node(public_domain="fr2.example.com", reality_ip="198.51.100.11", region="fr")
    node_2.id = uuid4()
    tp = _make_transport_profile(network="tcp", security="reality")
    key = _make_bundle("reality").keys[0]
    route_1 = ResolvedSubscriptionRoute(
        route_id=uuid4(),
        backend_node_id=node.id,
        vpn_key_id=key.vpn_key_id,
        vpn_transport="reality",
        client_id=key.client_id,
        transport_security="reality",
        transport_network="tcp",
        country_code="FR",
        country_name="France",
        display_name="\U0001f1eb\U0001f1f7 France Reality",
        preferred_backend=True,
        selection_rank=0,
        uri="vless://fr-reality#%F0%9F%87%AB%F0%9F%87%B7%20France%20Reality",
        route=route,
        node=node,
        transport_profile=tp,
    )
    route_2 = route_1.model_copy(
        update={
            "route_id": uuid4(),
            "backend_node_id": node_2.id,
            "uri": "vless://fr-reality-2#%F0%9F%87%AB%F0%9F%87%B7%20France%20Reality",
            "preferred_backend": False,
            "node": node_2,
        }
    )

    merged = service._merge_transport_routes(
        subscription=_make_sub(preferred_region="fr"),
        transport_results=[
            TransportBuildResult(
                key=key,
                routes=(route_1, route_2),
                placement_signature="reality:1",
                diagnostic_reason=None,
            )
        ],
    )

    assert len(merged) == 2
    assert "1" in merged[0].display_name
    assert "2" in merged[1].display_name
    assert "WL" not in merged[0].display_name
    assert "WL" not in merged[1].display_name


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
    sub.hwid_enabled = True
    sub.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    sub.is_active = True
    service.subscription_repository.create = AsyncMock(return_value=sub)
    service.vpn_key_repository.create = AsyncMock()

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
    service.vpn_key_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_subscription_url_uses_base_url_as_is(service):
    user_id = uuid4()
    service.settings.subscriptions.public_base_url = "https://api.example.com/custom-prefix/"
    service.user_repository.get_by_id = AsyncMock(return_value=MagicMock())
    sub = MagicMock()
    sub.id = uuid4()
    sub.client_id = uuid4()
    sub.hwid_enabled = True
    sub.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    sub.is_active = True
    service.subscription_repository.create = AsyncMock(return_value=sub)
    service.vpn_key_repository.create = AsyncMock()

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
    service.vpn_key_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_subscription_invalid_profile_lists_available_keys(service):
    from shared.profiles.exceptions import ProfileRegistryError

    user_id = uuid4()
    service.user_repository.get_by_id = AsyncMock(return_value=MagicMock())

    with patch("services.vpn.subscriptions.service.ProfileRegistry.get") as get_profile:
        with patch(
            "services.vpn.subscriptions.service.ProfileRegistry.all_keys",
            return_value=["reality_tcp_dev_v1", "ws_tls_dev_v1"],
        ):
            get_profile.side_effect = ProfileRegistryError("Profile not found: ws_tls_v1")

            with pytest.raises(HTTPException) as exc_info:
                await service.create(
                    SubscriptionCreateIn(
                        user_id=user_id,
                        profile_key="ws_tls_v1",
                    )
                )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == (
        "Profile not found: ws_tls_v1. Available profile keys: reality_tcp_dev_v1, ws_tls_dev_v1"
    )


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


@pytest.mark.asyncio
async def test_subscription_returns_new_target_placement_even_when_not_synced(service):
    backend = MagicMock()
    backend.id = uuid4()
    backend.public_domain = "be.example.com"
    backend.reality_ip = "203.0.113.20"
    backend.role = "backend"
    backend.region = "fi"
    backend.is_active = True
    backend.is_enabled = True
    backend.is_draining = False

    created = MagicMock(
        id=uuid4(),
        key_id=uuid4(),
        backend_node_id=backend.id,
        desired_state="active",
        op_version=3,
        applied_version=0,
        applied_state="pending",
    )

    service.placement_repository = AsyncMock()
    service.node_agent_transport = AsyncMock()
    service.routing_service = AsyncMock()
    service.placement_repository.list_by_key_id.return_value = []
    service.placement_repository.upsert_set_pending = AsyncMock(return_value=created)
    service.routing_service.select_nodes = AsyncMock(return_value=[backend])

    preferred_backend_id, placement, allowed_backend_ids = await service._ensure_backend_placements_for_key(
        key_id=uuid4(),
        preferred_region="fi",
        desired_replicas=1,
        key_transport="reality",
    )

    assert preferred_backend_id == backend.id
    assert placement.id == created.id
    assert allowed_backend_ids == {backend.id}
    service.node_agent_transport.enqueue_for_placement_ids.assert_awaited_once_with([created.id])


@pytest.mark.asyncio
async def test_subscription_returns_synced_existing_placement(service):
    backend = MagicMock()
    backend.id = uuid4()
    backend.public_domain = "be.example.com"
    backend.reality_ip = "203.0.113.20"
    backend.role = "backend"
    backend.region = "fi"
    backend.is_active = True
    backend.is_enabled = True
    backend.is_draining = False

    applied = MagicMock(
        id=uuid4(),
        key_id=uuid4(),
        backend_node_id=backend.id,
        desired_state="active",
        op_version=7,
        applied_version=7,
        applied_state="applied",
    )

    service.placement_repository = AsyncMock()
    service.routing_service = AsyncMock()
    service.placement_repository.list_by_key_id.return_value = [applied]
    service.routing_service.select_nodes = AsyncMock(return_value=[backend])

    preferred_backend_id, placement, allowed_backend_ids = await service._ensure_backend_placements_for_key(
        key_id=uuid4(),
        preferred_region="fi",
        desired_replicas=1,
        key_transport="reality",
    )

    assert preferred_backend_id == backend.id
    assert placement is applied
    assert allowed_backend_ids == {backend.id}


@pytest.mark.asyncio
async def test_subscription_returns_existing_target_placement_even_when_not_synced(service):
    backend = MagicMock()
    backend.id = uuid4()
    backend.public_domain = "be.example.com"
    backend.reality_ip = "203.0.113.20"
    backend.role = "backend"
    backend.region = "fi"
    backend.is_active = True
    backend.is_enabled = True
    backend.is_draining = False

    pending = MagicMock(
        id=uuid4(),
        key_id=uuid4(),
        backend_node_id=backend.id,
        desired_state="active",
        op_version=7,
        applied_version=0,
        applied_state="pending",
    )

    service.placement_repository = AsyncMock()
    service.routing_service = AsyncMock()
    service.placement_repository.list_by_key_id.return_value = [pending]
    service.routing_service.select_nodes = AsyncMock(return_value=[backend])

    preferred_backend_id, placement, allowed_backend_ids = await service._ensure_backend_placements_for_key(
        key_id=uuid4(),
        preferred_region="fi",
        desired_replicas=1,
        key_transport="reality",
    )

    assert preferred_backend_id == backend.id
    assert placement.id == pending.id
    assert allowed_backend_ids == {backend.id}


@pytest.mark.asyncio
async def test_build_payload_excludes_entry_routes_when_plan_has_no_whitelist(service):
    service.settings.subscriptions.response_cache_ttl_sec = 0
    service._enforce_rate_limit = AsyncMock()

    plan = MagicMock()
    plan.whitelist_enabled = False
    sub = _make_sub(preferred_region="fi")
    sub.plan = plan

    service.subscription_repository.get_by_any_token_hash.return_value = sub
    service._resolve_device_bundle_for_request = AsyncMock(
        return_value=_make_bundle("reality")
    )

    node = _make_node(reality_ip="198.51.100.10", region="fi")
    node.id = uuid4()
    route = MagicMock()
    route.id = uuid4()
    route.health_status = "healthy"
    route.effective_weight = 100
    tp = _make_transport_profile()

    async def _build_transport(*, subscription, key, max_routes):
        return TransportBuildResult(
            key=key,
            routes=(
                ResolvedSubscriptionRoute(
                    route_id=uuid4(),
                    backend_node_id=node.id,
                    vpn_key_id=key.vpn_key_id,
                    vpn_transport=key.transport,
                    client_id=key.client_id,
                    transport_security="reality",
                    transport_network="tcp",
                    country_code="FI",
                    country_name="Finland",
                    display_name="Finland",
                    preferred_backend=True,
                    selection_rank=0,
                    uri="vless://fi-direct#Finland",
                    route=route,
                    node=node,
                    transport_profile=tp,
                ),
            ),
            placement_signature="reality:1",
            diagnostic_reason=None,
        )

    service._build_transport_routes = AsyncMock(side_effect=_build_transport)
    payload, etag, _ = await service.build_payload(raw_token="tok", hwid="hwid-1")

    assert "fi-direct" in payload


@pytest.mark.asyncio
async def test_build_payload_includes_entry_routes_when_plan_whitelist_enabled(service):
    service.settings.subscriptions.response_cache_ttl_sec = 0
    service._enforce_rate_limit = AsyncMock()

    plan = MagicMock()
    plan.whitelist_enabled = True
    sub = _make_sub(preferred_region="fi")
    sub.plan = plan

    service.subscription_repository.get_by_any_token_hash.return_value = sub
    service._resolve_device_bundle_for_request = AsyncMock(
        return_value=_make_bundle("reality")
    )

    node = _make_node(reality_ip="198.51.100.10", region="fi")
    node.id = uuid4()
    route = MagicMock()
    route.id = uuid4()
    route.health_status = "healthy"
    route.effective_weight = 100
    tp = _make_transport_profile()

    async def _build_transport(*, subscription, key, max_routes):
        return TransportBuildResult(
            key=key,
            routes=(
                ResolvedSubscriptionRoute(
                    route_id=uuid4(),
                    backend_node_id=node.id,
                    vpn_key_id=key.vpn_key_id,
                    vpn_transport=key.transport,
                    client_id=key.client_id,
                    transport_security="reality",
                    transport_network="tcp",
                    country_code="FI",
                    country_name="Finland",
                    display_name="Finland WL",
                    is_entry_route=True,
                    preferred_backend=True,
                    selection_rank=0,
                    uri="vless://fi-wl#Finland%20WL",
                    route=route,
                    node=node,
                    transport_profile=tp,
                ),
            ),
            placement_signature="reality:1",
            diagnostic_reason=None,
        )

    service._build_transport_routes = AsyncMock(side_effect=_build_transport)
    payload, etag, _ = await service.build_payload(raw_token="tok", hwid="hwid-1")

    assert "fi-wl" in payload
