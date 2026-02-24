from services.config import get_settings


def test_probe_target_port_uses_probe_target_port(monkeypatch):
    monkeypatch.setenv("PROBE_TARGET_PORT", "2053")
    monkeypatch.setenv("DEFAULT_TARGET_PORT", "443")

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.probe.target_port == 2053
    get_settings.cache_clear()


def test_probe_target_port_does_not_use_legacy_default_target_port(monkeypatch):
    monkeypatch.delenv("PROBE_TARGET_PORT", raising=False)
    monkeypatch.setenv("DEFAULT_TARGET_PORT", "2053")

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.probe.target_port != 2053
    get_settings.cache_clear()
