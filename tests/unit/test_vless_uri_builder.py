from __future__ import annotations

import pytest

from shared.profiles.builder import VlessUriBuilder
from shared.profiles.exceptions import ProfileRegionMismatchError
from shared.profiles.schemas import (
    NodePublic,
    WsTlsProfile,
    WsTlsClientConfig,
    RealityTcpProfile,
    RealityTcpClientConfig,
    ProfileMetadata,
    ProfileType,
)
from shared.profiles.transport import VlessUri


# ── fixtures ──

def _ws_profile(**meta_kw) -> WsTlsProfile:
    return WsTlsProfile(
        type=ProfileType.ws_tls,
        client=WsTlsClientConfig(path="/ws", host="cdn.example.com", sni="cdn.example.com"),
        metadata=ProfileMetadata(display_name="WS TLS", **meta_kw),
    )


def _reality_profile(**meta_kw) -> RealityTcpProfile:
    return RealityTcpProfile(
        type=ProfileType.reality_tcp,
        client=RealityTcpClientConfig(
            sni="www.cloudflare.com",
            fingerprint="chrome",
            public_key="AAAAAAAAAAAAAAAA",
            short_id="abcd1234",
        ),
        metadata=ProfileMetadata(display_name="Reality TCP", **meta_kw),
    )


def _node(**kw) -> NodePublic:
    defaults = dict(domain="vpn.example.com", port=443, remark="Node1")
    defaults.update(kw)
    return NodePublic(**defaults)


# ── VlessUri.render ──

class TestVlessUriRender:
    def test_basic_render(self):
        uri = VlessUri(
            client_id="abc-123",
            host="vpn.example.com",
            port=443,
            query={"type": "ws", "security": "tls", "sni": "cdn.example.com"},
            remark="My Node",
        )
        rendered = uri.render()
        assert rendered.startswith("vless://abc-123@vpn.example.com:443?")
        assert "type=ws" in rendered
        assert "sni=cdn.example.com" in rendered
        assert rendered.endswith("#My%20Node")

    def test_render_no_remark(self):
        uri = VlessUri(
            client_id="id", host="h", port=1, query={"k": "v"}, remark=""
        )
        assert "#" not in uri.render()

    def test_render_server_description_base64_in_fragment(self):
        import base64
        uri = VlessUri(
            client_id="id", host="h", port=1, query={"k": "v"},
            remark="🇪🇺 Europe + WL unblock",
            server_description="🔓 глушилки",
        )
        rendered = uri.render()
        assert "#" in rendered
        fragment = rendered.split("#", 1)[1]
        assert "?serverDescription=" in fragment
        encoded = fragment.split("?serverDescription=", 1)[1]
        assert base64.b64decode(encoded).decode("utf-8") == "🔓 глушилки"

    def test_render_server_description_without_remark_still_in_fragment(self):
        uri = VlessUri(
            client_id="id", host="h", port=1, query={"k": "v"},
            remark="",
            server_description="🔓 глушилки",
        )
        rendered = uri.render()
        query_section = rendered.split("?", 1)[1]
        assert "serverDescription" not in query_section.split("#", 1)[0]
        assert "#" in rendered
        assert "?serverDescription=" in rendered.split("#", 1)[1]


# ── VlessUriBuilder.build — WS-TLS ──

class TestBuildWsTls:
    def test_ws_tls_uri_format(self):
        result = VlessUriBuilder.build(
            client_id="cid",
            node=_node(),
            profile=_ws_profile(),
        )
        assert result.startswith("vless://cid@vpn.example.com:443?")
        assert "type=ws" in result
        assert "security=tls" in result

    def test_ws_tls_remark_from_node(self):
        result = VlessUriBuilder.build(
            client_id="cid",
            node=_node(remark="MyRemark"),
            profile=_ws_profile(),
        )
        assert "MyRemark" in result


# ── VlessUriBuilder.build — Reality TCP ──

class TestBuildRealityTcp:
    def test_reality_tcp_uri_format(self):
        result = VlessUriBuilder.build(
            client_id="cid",
            node=_node(),
            profile=_reality_profile(),
        )
        assert result.startswith("vless://cid@vpn.example.com:443?")
        assert "security=reality" in result
        assert "type=tcp" in result
        assert "flow=xtls-rprx-vision" in result

    def test_reality_tcp_custom_flow(self):
        prof = _reality_profile()
        prof.client.flow = "custom-flow"
        result = VlessUriBuilder.build(
            client_id="cid",
            node=_node(),
            profile=prof,
        )
        assert "flow=custom-flow" in result


# ── IPv6 formatting ──

class TestIPv6Formatting:
    def test_ipv6_bracketed(self):
        result = VlessUriBuilder.build(
            client_id="cid",
            node=_node(domain="::1"),
            profile=_ws_profile(),
        )
        assert "[::1]" in result

    def test_ipv6_already_bracketed(self):
        result = VlessUriBuilder.build(
            client_id="cid",
            node=_node(domain="[::1]"),
            profile=_ws_profile(),
        )
        # should not double-bracket
        assert "[::1]" in result
        assert "[[" not in result

    def test_ipv4_no_brackets(self):
        result = VlessUriBuilder.build(
            client_id="cid",
            node=_node(domain="1.2.3.4"),
            profile=_ws_profile(),
        )
        assert "1.2.3.4" in result
        assert "[1.2.3.4]" not in result


# ── Region mismatch ──

class TestRegionMismatch:
    def test_region_mismatch_raises(self):
        profile = _ws_profile(region_support=["de", "nl"])
        node = _node(region="us")
        with pytest.raises(ProfileRegionMismatchError):
            VlessUriBuilder.build(client_id="cid", node=node, profile=profile)

    def test_region_match_ok(self):
        profile = _ws_profile(region_support=["de", "nl"])
        node = _node(region="de")
        result = VlessUriBuilder.build(client_id="cid", node=node, profile=profile)
        assert "vless://" in result

    def test_no_region_support_allows_all(self):
        profile = _ws_profile()  # no region_support
        node = _node(region="us")
        result = VlessUriBuilder.build(client_id="cid", node=node, profile=profile)
        assert "vless://" in result
