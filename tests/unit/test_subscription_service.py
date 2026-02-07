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
)
from shared.profiles.registry import ProfileRegistry
from shared.profiles.schemas import (
    WsTlsProfile,
    WsTlsClientConfig,
    RealityTcpProfile,
    RealityTcpClientConfig,
    ProfileMetadata,
    ProfileType,
    NodePublic,
)


WS_TLS_RAW = {
    "type": "ws_tls",
    "client": {"path": "/ws", "host": "cdn.example.com", "sni": "cdn.example.com"},
    "metadata": {"display_name": "WS TLS"},
}

REALITY_TCP_RAW = {
    "type": "reality_tcp",
    "client": {
        "sni": "www.cloudflare.com",
        "flow": "xtls-rprx-vision",
        "fingerprint": "chrome",
        "public_key": "AAAAAAAAAAAAAAAA",
        "short_id": "abcd1234",
    },
    "metadata": {"display_name": "Reality TCP"},
}


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


class TestBuildUris:
    def test_nodes_x_profiles(self, service):
        ProfileRegistry.register("ws1", WS_TLS_RAW)
        profiles = [ProfileRegistry.get("ws1").profile]
        nodes = [_make_node(), _make_node(public_domain="vpn2.example.com", name="node2")]

        uris = service._build_uris(
            client_id="cid",
            nodes=nodes,
            profiles=profiles,
        )
        assert len(uris) == 2
        assert all(u.startswith("vless://") for u in uris)

    def test_region_mismatch_skipped(self, service):
        raw = {**WS_TLS_RAW, "metadata": {"display_name": "WS", "region_support": ["de"]}}
        ProfileRegistry.register("ws_de", raw)
        profiles = [ProfileRegistry.get("ws_de").profile]
        node_us = _make_node(region="us")

        uris = service._build_uris(client_id="cid", nodes=[node_us], profiles=profiles)
        assert uris == []

    def test_empty_nodes(self, service):
        ProfileRegistry.register("ws1", WS_TLS_RAW)
        profiles = [ProfileRegistry.get("ws1").profile]
        uris = service._build_uris(client_id="cid", nodes=[], profiles=profiles)
        assert uris == []


class TestCalcEtag:
    def test_deterministic(self, service):
        sub = _make_sub()
        node = MagicMock()
        node.public_domain = "vpn.example.com"
        profile = MagicMock()
        profile.type = "ws_tls"
        profile.version = 1

        e1 = service._calc_etag(sub, [node], [profile])
        e2 = service._calc_etag(sub, [node], [profile])
        assert e1 == e2
        assert len(e1) == 64  # sha256 hex

    def test_different_sub_different_etag(self, service):
        sub1 = _make_sub()
        sub2 = _make_sub()
        node = MagicMock()
        node.public_domain = "vpn.example.com"
        profile = MagicMock()
        profile.type = "ws_tls"
        profile.version = 1

        e1 = service._calc_etag(sub1, [node], [profile])
        e2 = service._calc_etag(sub2, [node], [profile])
        # different UUIDs → different etags
        assert e1 != e2
