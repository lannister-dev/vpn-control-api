from __future__ import annotations

import pytest

from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.registry import ProfileRegistry


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


class TestProfileRegistryRegister:
    def test_register_ws_tls(self):
        ProfileRegistry.register("ws1", WS_TLS_RAW)
        cfg = ProfileRegistry.get("ws1")
        assert cfg.key == "ws1"
        assert cfg.profile.metadata.display_name == "WS TLS"

    def test_register_reality_tcp(self):
        ProfileRegistry.register("rt1", REALITY_TCP_RAW)
        cfg = ProfileRegistry.get("rt1")
        assert cfg.key == "rt1"

    def test_duplicate_key_raises(self):
        ProfileRegistry.register("dup", WS_TLS_RAW)
        with pytest.raises(ProfileRegistryError, match="already registered"):
            ProfileRegistry.register("dup", WS_TLS_RAW)

    def test_unknown_type_raises(self):
        raw = {**WS_TLS_RAW, "type": "unknown_proto"}
        with pytest.raises(ProfileRegistryError, match="Unknown profile type"):
            ProfileRegistry.register("x", raw)

    def test_missing_type_raises(self):
        raw = {"client": WS_TLS_RAW["client"], "metadata": WS_TLS_RAW["metadata"]}
        with pytest.raises(ProfileRegistryError, match="Unknown profile type"):
            ProfileRegistry.register("x", raw)


class TestProfileRegistryFreeze:
    def test_frozen_prevents_register(self):
        ProfileRegistry.register("ws1", WS_TLS_RAW)
        ProfileRegistry.freeze()
        with pytest.raises(ProfileRegistryError, match="frozen"):
            ProfileRegistry.register("ws2", REALITY_TCP_RAW)

    def test_reset_unfreezes(self):
        ProfileRegistry.register("ws1", WS_TLS_RAW)
        ProfileRegistry.freeze()
        ProfileRegistry.reset()
        ProfileRegistry.register("ws1", WS_TLS_RAW)
        assert ProfileRegistry.get("ws1").key == "ws1"


class TestProfileRegistryGet:
    def test_get_unknown_key(self):
        with pytest.raises(ProfileRegistryError, match="not found"):
            ProfileRegistry.get("nope")


class TestProfileRegistryAllKeys:
    def test_all_keys(self):
        ProfileRegistry.register("a", WS_TLS_RAW)
        ProfileRegistry.register("b", REALITY_TCP_RAW)
        assert set(ProfileRegistry.all_keys()) == {"a", "b"}


class TestProfileRegistryValidateNonEmpty:
    def test_empty_raises(self):
        with pytest.raises(ProfileRegistryError, match="No profiles"):
            ProfileRegistry.validate_non_empty()

    def test_non_empty_ok(self):
        ProfileRegistry.register("ws1", WS_TLS_RAW)
        ProfileRegistry.validate_non_empty()


class TestBootstrapFromDict:
    def test_bootstrap_ok(self):
        ProfileRegistry.bootstrap_from_dict({"ws": WS_TLS_RAW, "rt": REALITY_TCP_RAW})
        assert ProfileRegistry._frozen is True
        assert set(ProfileRegistry.all_keys()) == {"ws", "rt"}

    def test_bootstrap_empty_raises(self):
        with pytest.raises(ProfileRegistryError, match="No profiles"):
            ProfileRegistry.bootstrap_from_dict({})

    def test_bootstrap_invalid_profile_raises(self):
        bad = {**WS_TLS_RAW, "type": "bad"}
        with pytest.raises(ProfileRegistryError, match="Invalid profiles"):
            ProfileRegistry.bootstrap_from_dict({"bad": bad})


class TestReloadFromDict:
    def test_reload_replaces_profiles(self):
        ProfileRegistry.register("old", WS_TLS_RAW)
        ProfileRegistry.freeze()

        ProfileRegistry.reload_from_dict(
            {
                "new_ws": {
                    "type": "ws_tls",
                    "display_name": "New WS",
                    "client": {"path": "/ws", "host": "x.com", "sni": "x.com"},
                }
            },
            artifact_version=2,
        )
        assert "new_ws" in ProfileRegistry.all_keys()
        assert "old" not in ProfileRegistry.all_keys()
        assert ProfileRegistry._artifact_version == 2
        assert ProfileRegistry._frozen is True

    def test_reload_empty_raises(self):
        with pytest.raises(ProfileRegistryError, match="No profiles"):
            ProfileRegistry.reload_from_dict({}, artifact_version=1)

    def test_reload_invalid_raises(self):
        with pytest.raises(ProfileRegistryError, match="Invalid profiles"):
            ProfileRegistry.reload_from_dict(
                {"bad": {"type": "ws_tls", "display_name": "X", "client": {}}},
                artifact_version=1,
            )
