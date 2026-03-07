from __future__ import annotations

from shared.profiles.artifact_mapper import ArtifactProfileMapper


def _artifact() -> dict:
    return {
        "reality-google": {
            "type": "reality_tcp",
            "display_name": "Reality Google",
            "client": {
                "sni": "www.google.com",
                "flow": "xtls-rprx-vision",
                "fingerprint": "chrome",
                "public_key": "PUBLIC_KEY_1234567890",
                "short_id": "abcd1234",
            },
        },
        "ws-backup": {
            "type": "ws_tls",
            "display_name": "WS Backup",
            "client": {"path": "/ws", "host": "cdn.example.com", "sni": "cdn.example.com"},
        },
    }


def test_project_artifact_profiles_default_policy():
    projection = ArtifactProfileMapper(
        include_reality_tcp=True,
        include_ws_tls=False,
    )
    projected = projection.map(_artifact())
    desired = projected.desired_profiles
    skipped = projected.skipped_profiles
    total = projected.profiles_total

    assert total == 2
    assert len(desired) == 1
    assert desired[0].name == "reality-google"
    assert desired[0].network == "tcp"
    assert desired[0].security == "reality"
    assert desired[0].port == 443
    assert any("ws-backup" in item for item in skipped)


def test_project_artifact_profiles_with_ws_enabled_and_port_override():
    projection = ArtifactProfileMapper(
        include_reality_tcp=True,
        include_ws_tls=True,
        profile_port_overrides={"ws-backup": 8443},
    )
    projected = projection.map(_artifact())
    desired = projected.desired_profiles
    skipped = projected.skipped_profiles
    total = projected.profiles_total

    assert total == 2
    assert len(desired) == 2
    by_key = {item.artifact_key: item for item in desired}
    assert by_key["ws-backup"].network == "ws"
    assert by_key["ws-backup"].security == "tls"
    assert by_key["ws-backup"].port == 8443
    assert skipped == []


def test_normalize_bootstrap_entity_name_trims_and_hashes_long_value():
    raw = "  VERY LONG NAME ### " + ("x" * 200)
    out = ArtifactProfileMapper.normalize_name(key=raw, max_len=32)

    assert len(out) <= 32
    assert out.startswith("very-long-name")
    assert "-" in out
