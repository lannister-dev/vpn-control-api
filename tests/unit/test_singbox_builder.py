"""Unit tests for sing-box subscription generator."""
from __future__ import annotations

import json

import pytest

from services.vpn.subscriptions.singbox_builder import (
    SingboxBuildError,
    SingboxConfig,
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
    def test_reality_tcp(self):
        out = _vless_uri_to_outbound(REALITY_URI, tag="primary")
        assert out["type"] == "vless"
        assert out["tag"] == "primary"
        assert out["server"] == "example.com"
        assert out["server_port"] == 443
        assert out["uuid"] == "11111111-2222-3333-4444-555555555555"
        assert out["flow"] == "xtls-rprx-vision"
        assert out["packet_encoding"] == "xudp"
        # tcp → no transport block
        assert "transport" not in out
        tls = out["tls"]
        assert tls["enabled"] is True
        assert tls["server_name"] == "apple.com"
        assert tls["utls"]["fingerprint"] == "chrome"
        assert tls["reality"]["public_key"] == "abcDEFpubkey"
        assert tls["reality"]["short_id"] == "ad12"

    def test_ws_tls(self):
        out = _vless_uri_to_outbound(WS_TLS_URI, tag="ws")
        assert out["transport"]["type"] == "ws"
        assert out["transport"]["path"] == "/api/v1/stream"
        assert out["transport"]["headers"] == {"Host": "gw.example.com"}
        assert out["tls"]["server_name"] == "gw.example.com"
        assert out["tls"]["utls"]["fingerprint"] == "firefox"
        assert "reality" not in out["tls"]
        assert "flow" not in out

    def test_grpc(self):
        out = _vless_uri_to_outbound(GRPC_URI, tag="grpc")
        assert out["transport"] == {"type": "grpc", "service_name": "vl"}
        assert out["tls"]["server_name"] == "rly.example.com"

    def test_invalid_scheme_raises(self):
        with pytest.raises(SingboxBuildError):
            _vless_uri_to_outbound("ss://...", tag="x")

    def test_missing_fields_raises(self):
        with pytest.raises(SingboxBuildError):
            _vless_uri_to_outbound("vless://@host:443?", tag="x")


class TestSingboxConfig:
    def test_zone_without_fallback_emits_single_outbound_named_after_zone(self):
        cfg = SingboxConfig(grouped_zones=[
            ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI),
        ])
        d = cfg.to_dict()
        outs = d["outbounds"]
        # 1 vless + direct + block
        assert [o["tag"] for o in outs] == ["Europe", "direct", "block"]
        assert outs[0]["type"] == "vless"

    def test_zone_with_fallback_emits_urltest_group(self):
        cfg = SingboxConfig(grouped_zones=[
            ZoneOutbounds(
                tag="Europe",
                primary_uri=REALITY_URI,
                fallback_uri=WHITELIST_URI,
            ),
        ])
        d = cfg.to_dict()
        outs = {o["tag"]: o for o in d["outbounds"]}
        assert "Europe · primary" in outs
        assert "Europe · fallback" in outs
        assert "Europe" in outs
        group = outs["Europe"]
        assert group["type"] == "urltest"
        assert group["outbounds"] == ["Europe · primary", "Europe · fallback"]
        assert group["tolerance"] == 10000
        assert group["interrupt_exist_connections"] is False
        assert group["interval"] == "30s"

    def test_multiple_zones_and_extras(self):
        cfg = SingboxConfig(
            grouped_zones=[
                ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI, fallback_uri=WHITELIST_URI),
                ZoneOutbounds(tag="NL", primary_uri=WS_TLS_URI),
            ],
            extra_outbounds=[("FR", GRPC_URI)],
        )
        d = cfg.to_dict()
        tags = [o["tag"] for o in d["outbounds"]]
        # Europe has primary + fallback + urltest group; NL plain; FR plain; +direct +block
        assert tags == [
            "Europe · primary",
            "Europe · fallback",
            "Europe",
            "NL",
            "FR",
            "direct",
            "block",
        ]

    def test_to_json_is_compact_and_valid(self):
        cfg = SingboxConfig(grouped_zones=[
            ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI, fallback_uri=WHITELIST_URI),
        ])
        body = cfg.to_json()
        # Compact separators — no whitespace between JSON tokens.
        assert ": " not in body and ", " not in body
        parsed = json.loads(body)
        assert "outbounds" in parsed
