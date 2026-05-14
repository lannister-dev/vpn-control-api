from __future__ import annotations

import json

import pytest

from services.vpn.subscriptions.xray_json_builder import (
    XrayBuildError,
    XrayJsonConfig,
    ZoneOutbounds,
    _vless_uri_to_outbound,
)

REALITY_URI = (
    "vless://11111111-2222-3333-4444-555555555555@example.com:443"
    "?type=tcp&security=reality&pbk=abcDEFpubkey&sid=ad12&sni=apple.com"
    "&fp=chrome&flow=xtls-rprx-vision#DE-entry"
)
WS_TLS_URI = (
    "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@gw.example.com:8443"
    "?type=ws&security=tls&sni=gw.example.com&path=%2Fapi%2Fv1%2Fstream"
    "&host=gw.example.com&fp=firefox#NL"
)
GRPC_URI = (
    "vless://abcd1234-aaaa-bbbb-cccc-deadbeefcafe@rly.example.com:443"
    "?type=grpc&security=tls&serviceName=vl&sni=rly.example.com&fp=chrome#FR"
)
WHITELIST_URI = (
    "vless://99999999-8888-7777-6666-555555555555@yc-relay.example.ru:443"
    "?type=tcp&security=reality&pbk=zzzPubKey&sid=00&sni=apple.com"
    "&fp=chrome&flow=xtls-rprx-vision#mow-whitelist"
)


class TestVlessUriToOutbound:
    def test_reality_tcp_shape(self):
        out = _vless_uri_to_outbound(REALITY_URI, tag="proxy")
        assert out["tag"] == "proxy"
        assert out["protocol"] == "vless"
        vnext = out["settings"]["vnext"][0]
        assert vnext["address"] == "example.com"
        assert vnext["port"] == 443
        user = vnext["users"][0]
        assert user["id"] == "11111111-2222-3333-4444-555555555555"
        assert user["encryption"] == "none"
        assert user["flow"] == "xtls-rprx-vision"
        stream = out["streamSettings"]
        assert stream["network"] == "tcp"
        assert stream["security"] == "reality"
        assert stream["realitySettings"]["publicKey"] == "abcDEFpubkey"
        assert stream["realitySettings"]["shortId"] == "ad12"
        assert stream["realitySettings"]["serverName"] == "apple.com"
        assert stream["realitySettings"]["fingerprint"] == "chrome"

    def test_ws_tls(self):
        out = _vless_uri_to_outbound(WS_TLS_URI, tag="proxy")
        stream = out["streamSettings"]
        assert stream["network"] == "ws"
        assert stream["wsSettings"]["path"] == "/api/v1/stream"
        assert stream["wsSettings"]["headers"] == {"Host": "gw.example.com"}
        assert stream["security"] == "tls"
        assert stream["tlsSettings"]["serverName"] == "gw.example.com"
        assert stream["tlsSettings"]["fingerprint"] == "firefox"
        assert "flow" not in out["settings"]["vnext"][0]["users"][0]

    def test_grpc(self):
        out = _vless_uri_to_outbound(GRPC_URI, tag="proxy")
        stream = out["streamSettings"]
        assert stream["network"] == "grpc"
        assert stream["grpcSettings"]["serviceName"] == "vl"
        assert stream["tlsSettings"]["serverName"] == "rly.example.com"

    def test_invalid_scheme_raises(self):
        with pytest.raises(XrayBuildError):
            _vless_uri_to_outbound("ss://...", tag="x")

    def test_missing_fields_raises(self):
        with pytest.raises(XrayBuildError):
            _vless_uri_to_outbound("vless://@host:443?", tag="x")


class TestXrayJsonConfig:
    def test_zone_without_fallback_emits_single_server_no_balancer(self):
        cfg = XrayJsonConfig(grouped_zones=[
            ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI),
        ])
        items = cfg.to_list()
        assert len(items) == 1
        item = items[0]
        assert item["remarks"] == "Europe"
        tags = [o["tag"] for o in item["outbounds"]]
        assert tags == ["proxy", "direct", "block"]
        rules = item["routing"]["rules"]
        assert {"type": "field", "network": "tcp,udp", "outboundTag": "proxy"} in rules
        assert "balancers" not in item["routing"]
        assert "observatory" not in item

    def test_zone_with_fallback_emits_balancer(self):
        cfg = XrayJsonConfig(grouped_zones=[
            ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI, fallback_uri=WHITELIST_URI),
        ])
        items = cfg.to_list()
        assert len(items) == 1
        item = items[0]
        assert item["remarks"] == "Europe"
        tags = [o["tag"] for o in item["outbounds"]]
        assert tags == ["proxy", "proxy-2", "direct", "block"]
        balancers = item["routing"]["balancers"]
        assert balancers == [
            {"tag": "balancer", "selector": ["proxy"], "strategy": {"type": "leastPing"}},
        ]
        rules = item["routing"]["rules"]
        assert {"type": "field", "network": "tcp,udp", "balancerTag": "balancer"} in rules
        assert item["observatory"]["subjectSelector"] == ["proxy"]

    def test_multiple_zones_and_extras_each_become_separate_servers(self):
        cfg = XrayJsonConfig(
            grouped_zones=[
                ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI, fallback_uri=WHITELIST_URI),
                ZoneOutbounds(tag="NL", primary_uri=WS_TLS_URI),
            ],
            extra_outbounds=[("FR", GRPC_URI)],
        )
        items = cfg.to_list()
        assert [i["remarks"] for i in items] == ["Europe", "NL", "FR"]
        # Europe has balancer, NL doesn't, FR doesn't
        assert "balancers" in items[0]["routing"]
        assert "balancers" not in items[1]["routing"]
        assert "balancers" not in items[2]["routing"]

    def test_to_json_is_compact_array(self):
        cfg = XrayJsonConfig(grouped_zones=[
            ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI, fallback_uri=WHITELIST_URI),
        ])
        body = cfg.to_json()
        assert body.startswith("[") and body.endswith("]")
        assert ": " not in body and ", " not in body
        parsed = json.loads(body)
        assert isinstance(parsed, list)
        assert parsed[0]["remarks"] == "Europe"
