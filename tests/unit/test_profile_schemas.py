from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.profiles.schemas import (
    ProfileMetadata,
    WsTlsClientConfig,
    RealityTcpClientConfig,
)


class TestProfileMetadata:
    def test_display_name_stripped(self):
        m = ProfileMetadata(display_name="  hello  ")
        assert m.display_name == "hello"

    def test_display_name_empty_raises(self):
        with pytest.raises(ValidationError):
            ProfileMetadata(display_name="")

    def test_region_support_from_string(self):
        m = ProfileMetadata(display_name="X", region_support="DE")
        assert m.region_support == ["de"]

    def test_region_support_dedup_and_lower(self):
        m = ProfileMetadata(display_name="X", region_support=["DE", "de", "NL"])
        assert m.region_support == ["de", "nl"]

    def test_region_support_none_becomes_empty(self):
        m = ProfileMetadata(display_name="X", region_support=None)
        assert m.region_support == []


class TestWsTlsClientConfig:
    def test_path_normalization_adds_slash(self):
        c = WsTlsClientConfig(path="ws", host="h.com", sni="h.com")
        assert c.path == "/ws"

    def test_path_already_slash(self):
        c = WsTlsClientConfig(path="/ws", host="h.com", sni="h.com")
        assert c.path == "/ws"

    def test_empty_path_raises(self):
        with pytest.raises(ValidationError):
            WsTlsClientConfig(path="", host="h.com", sni="h.com")


class TestRealityTcpClientConfig:
    def test_flow_none_resolve(self):
        c = RealityTcpClientConfig(
            sni="x.com", fingerprint="chrome",
            public_key="AAAAAAAAAAAAAAAA", short_id="abc",
        )
        assert c.flow is None
        assert c.resolve_flow() == "xtls-rprx-vision"

    def test_flow_empty_string_becomes_none(self):
        c = RealityTcpClientConfig(
            sni="x.com", fingerprint="chrome",
            public_key="AAAAAAAAAAAAAAAA", short_id="abc",
            flow="  ",
        )
        assert c.flow is None
        assert c.resolve_flow() == "xtls-rprx-vision"

    def test_flow_explicit(self):
        c = RealityTcpClientConfig(
            sni="x.com", fingerprint="chrome",
            public_key="AAAAAAAAAAAAAAAA", short_id="abc",
            flow="custom-flow",
        )
        assert c.resolve_flow() == "custom-flow"
