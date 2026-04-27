from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from services.config import K3sConfig
from services.nodes.installer import render_install_script


def _node(**overrides):
    base = dict(
        id=uuid4(),
        name="vpn-yc-entry-42",
        role="entry",
        region="ru-central1-d",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _settings_with_k3s(**k3s_overrides):
    defaults = dict(
        server_url="https://k3s-server.example:6443",
        node_token="K10::server:secret",
        version="v1.29.4+k3s1",
        bootstrap_token_ttl_sec=3600,
        public_base_url="https://control-api.example",
        channel="prod",
    )
    defaults.update(k3s_overrides)
    return SimpleNamespace(k3s=K3sConfig(**defaults))


def test_render_install_script_substitutes_variables():
    node = _node()
    with patch(
        "services.nodes.installer.get_settings",
        return_value=_settings_with_k3s(),
    ):
        script = render_install_script(node=node, raw_bootstrap_token="tok-abc")

    assert "{{ " not in script  # all placeholders substituted
    assert f'NODE_ID="{node.id}"' in script
    assert f'NODE_NAME="{node.name}"' in script
    assert f'TRAFFIC_ROLE="{node.role}"' in script
    assert f'NODE_REGION="{node.region}"' in script
    assert 'CHANNEL="prod"' in script
    assert 'K3S_URL="https://k3s-server.example:6443"' in script
    assert 'K3S_TOKEN="K10::server:secret"' in script
    assert 'K3S_VERSION="v1.29.4+k3s1"' in script
    assert 'CONTROL_API_URL="https://control-api.example"' in script
    assert 'BOOTSTRAP_TOKEN="tok-abc"' in script
    assert "--node-label=role=vpn" in script
    assert "--node-label=channel=${CHANNEL}" in script
    assert "--node-label=traffic_role=${TRAFFIC_ROLE}" in script


def test_render_install_script_raises_without_k3s_config():
    node = _node()
    with patch(
        "services.nodes.installer.get_settings",
        return_value=_settings_with_k3s(server_url="", node_token=""),
    ), pytest.raises(RuntimeError):
        render_install_script(node=node, raw_bootstrap_token="tok")


def test_render_install_script_raises_without_public_base_url():
    node = _node()
    with patch(
        "services.nodes.installer.get_settings",
        return_value=_settings_with_k3s(public_base_url=""),
    ), pytest.raises(RuntimeError):
        render_install_script(node=node, raw_bootstrap_token="tok")


def test_render_install_script_rejects_dangerous_node_name():
    node = _node(name='evil"; rm -rf /')
    with patch(
        "services.nodes.installer.get_settings",
        return_value=_settings_with_k3s(),
    ), pytest.raises(ValueError):
        render_install_script(node=node, raw_bootstrap_token="tok")


def test_render_install_script_rejects_backtick_in_token():
    node = _node()
    with patch(
        "services.nodes.installer.get_settings",
        return_value=_settings_with_k3s(),
    ), pytest.raises(ValueError):
        render_install_script(node=node, raw_bootstrap_token="tok`whoami`")


def test_render_install_script_fills_unknown_region_when_empty():
    node = _node(region=None)
    with patch(
        "services.nodes.installer.get_settings",
        return_value=_settings_with_k3s(),
    ):
        script = render_install_script(node=node, raw_bootstrap_token="tok")
    assert 'NODE_REGION="unknown"' in script


def test_render_install_script_raises_when_channel_missing():
    node = _node()
    with patch(
        "services.nodes.installer.get_settings",
        return_value=_settings_with_k3s(channel=""),
    ), pytest.raises(RuntimeError):
        render_install_script(node=node, raw_bootstrap_token="tok")


def test_render_install_script_raises_on_invalid_channel():
    node = _node()
    with patch(
        "services.nodes.installer.get_settings",
        return_value=_settings_with_k3s(channel="staging"),
    ), pytest.raises(RuntimeError):
        render_install_script(node=node, raw_bootstrap_token="tok")
