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


class TestSingboxConfigTopLevel:
    def test_full_config_has_required_sections(self):
        cfg = SingboxConfig(grouped_zones=[ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI)])
        d = cfg.to_dict()
        assert set(d.keys()) >= {"log", "dns", "inbounds", "outbounds", "route"}

    def test_route_final_points_to_selector(self):
        cfg = SingboxConfig(grouped_zones=[ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI)])
        d = cfg.to_dict()
        assert d["route"]["final"] == "proxy"
        rules = d["route"]["rules"]
        assert {"protocol": "dns", "outbound": "dns-out"} in rules
        assert {"ip_is_private": True, "outbound": "direct"} in rules

    def test_inbounds_has_tun(self):
        cfg = SingboxConfig(grouped_zones=[ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI)])
        d = cfg.to_dict()
        tun = next((i for i in d["inbounds"] if i["type"] == "tun"), None)
        assert tun is not None
        assert tun["auto_route"] is True

    def test_dns_has_servers_and_rules(self):
        cfg = SingboxConfig(grouped_zones=[ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI)])
        d = cfg.to_dict()
        assert any(s["tag"] == "cf-dns" for s in d["dns"]["servers"])


class TestSingboxConfigOutbounds:
    def _by_tag(self, outbounds):
        return {o["tag"]: o for o in outbounds}

    def test_zone_without_fallback_emits_single_vless(self):
        cfg = SingboxConfig(grouped_zones=[
            ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI),
        ])
        outs = self._by_tag(cfg.to_dict()["outbounds"])
        assert outs["proxy"]["type"] == "selector"
        assert outs["proxy"]["outbounds"] == ["Europe"]
        assert outs["Europe"]["type"] == "vless"
        assert "direct" in outs and "block" in outs and "dns-out" in outs

    def test_zone_with_fallback_emits_urltest_in_selector(self):
        cfg = SingboxConfig(grouped_zones=[
            ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI, fallback_uri=WHITELIST_URI),
        ])
        outs = self._by_tag(cfg.to_dict()["outbounds"])
        assert outs["proxy"]["outbounds"] == ["Europe"]
        assert outs["Europe · primary"]["type"] == "vless"
        assert outs["Europe · fallback"]["type"] == "vless"
        group = outs["Europe"]
        assert group["type"] == "urltest"
        assert group["outbounds"] == ["Europe · primary", "Europe · fallback"]
        assert group["tolerance"] == 10000
        assert group["interrupt_exist_connections"] is False

    def test_multi_zone_selector_lists_all_user_visible(self):
        cfg = SingboxConfig(
            grouped_zones=[
                ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI, fallback_uri=WHITELIST_URI),
                ZoneOutbounds(tag="NL", primary_uri=WS_TLS_URI),
            ],
            extra_outbounds=[("FR", GRPC_URI)],
        )
        outs = self._by_tag(cfg.to_dict()["outbounds"])
        assert outs["proxy"]["outbounds"] == ["Europe", "NL", "FR"]
        assert outs["proxy"]["default"] == "Europe"

    def test_to_json_is_compact_and_valid(self):
        cfg = SingboxConfig(grouped_zones=[
            ZoneOutbounds(tag="Europe", primary_uri=REALITY_URI, fallback_uri=WHITELIST_URI),
        ])
        body = cfg.to_json()
        assert ": " not in body and ", " not in body
        parsed = json.loads(body)
        assert "outbounds" in parsed and "route" in parsed
