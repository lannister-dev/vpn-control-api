from services.config import get_settings


def test_probe_target_port_uses_legacy_default_target_port_when_new_name_missing(monkeypatch):
    monkeypatch.delenv("PROBE_TARGET_PORT", raising=False)
    monkeypatch.setenv("DEFAULT_TARGET_PORT", "2053")

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.probe.target_port == 2053
    get_settings.cache_clear()


def test_probe_target_port_new_name_has_priority_over_legacy(monkeypatch):
    monkeypatch.setenv("PROBE_TARGET_PORT", "443")
    monkeypatch.setenv("DEFAULT_TARGET_PORT", "2053")

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.probe.target_port == 443
    get_settings.cache_clear()
