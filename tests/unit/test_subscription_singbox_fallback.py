"""Tests for the urltest-fallback branch of subscription payload rendering."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.vpn.subscriptions.service import SubscriptionService

PRIMARY_URI = (
    "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@de-primary.example.com:443"
    "?type=tcp&security=reality&pbk=primaryPubKey&sid=ad12&sni=apple.com"
    "&fp=chrome&flow=xtls-rprx-vision#Europe"
)
FALLBACK_URI_BUILT = (
    "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@mow-relay.example.ru:443"
    "?type=tcp&security=reality&pbk=fallbackPubKey&sid=ff&sni=apple.com"
    "&fp=chrome&flow=xtls-rprx-vision#Europe"
)
PLAIN_URI = (
    "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@asia-be.example.com:443"
    "?type=tcp&security=reality&pbk=asiaPub&sid=01&sni=apple.com"
    "&fp=chrome&flow=xtls-rprx-vision#Asia"
)


def _make_route(*, uri: str, zone: str | None, display: str):
    backend = SimpleNamespace(zone=zone, name=f"be-{zone or 'x'}")
    return SimpleNamespace(
        uri=uri,
        node=backend,
        transport_profile=SimpleNamespace(),
        display_name=display,
        country_name=display,
    )


@pytest.fixture
def svc():
    s = SubscriptionService.__new__(SubscriptionService)
    s.session = MagicMock()
    s.zone_repository = MagicMock()
    s.node_repository = MagicMock()
    s._build_route_uri = MagicMock(return_value=FALLBACK_URI_BUILT)
    return s


@pytest.mark.asyncio
async def test_no_zones_falls_back_to_legacy_vless_list(svc):
    routes = [_make_route(uri=PLAIN_URI, zone=None, display="Asia")]
    out = await svc._render_subscription_payload(selected_routes=routes, client_id="cid")
    assert out == PLAIN_URI
    svc.zone_repository.list_by_codes = AsyncMock()  # not even called
    svc.zone_repository.list_by_codes.assert_not_called()


@pytest.mark.asyncio
async def test_zone_without_fallback_keeps_legacy(svc):
    zone = SimpleNamespace(code="europe", fallback_entry_node_id=None)
    svc.zone_repository.list_by_codes = AsyncMock(return_value=[zone])
    routes = [_make_route(uri=PRIMARY_URI, zone="europe", display="Europe")]
    out = await svc._render_subscription_payload(selected_routes=routes, client_id="cid")
    assert out == PRIMARY_URI
    svc.node_repository.list_by_ids = AsyncMock()
    svc.node_repository.list_by_ids.assert_not_called()


@pytest.mark.asyncio
async def test_zone_with_fallback_emits_singbox_json_with_urltest(svc):
    fallback_id = uuid4()
    zone = SimpleNamespace(code="europe", fallback_entry_node_id=fallback_id)
    fallback_node = SimpleNamespace(id=fallback_id, name="mow-whitelist")
    svc.zone_repository.list_by_codes = AsyncMock(return_value=[zone])
    svc.node_repository.list_by_ids = AsyncMock(return_value=[fallback_node])

    routes = [_make_route(uri=PRIMARY_URI, zone="europe", display="Europe")]
    out = await svc._render_subscription_payload(selected_routes=routes, client_id="cid")
    cfg = json.loads(out)
    tags = [o["tag"] for o in cfg["outbounds"]]
    assert "Europe · primary" in tags
    assert "Europe · fallback" in tags
    assert "Europe" in tags
    group = next(o for o in cfg["outbounds"] if o["tag"] == "Europe")
    assert group["type"] == "urltest"
    assert group["outbounds"] == ["Europe · primary", "Europe · fallback"]
    assert group["tolerance"] == 10000
    # _build_route_uri called for fallback with the whitelist node as public_node
    svc._build_route_uri.assert_called_once()
    kwargs = svc._build_route_uri.call_args.kwargs
    assert kwargs["public_node"] is fallback_node
    assert kwargs["client_id"] == "cid"


@pytest.mark.asyncio
async def test_mixed_zones_some_with_fallback_some_not(svc):
    fallback_id = uuid4()
    zone_eu = SimpleNamespace(code="europe", fallback_entry_node_id=fallback_id)
    zone_asia = SimpleNamespace(code="asia", fallback_entry_node_id=None)
    fallback_node = SimpleNamespace(id=fallback_id, name="mow-whitelist")
    svc.zone_repository.list_by_codes = AsyncMock(return_value=[zone_eu, zone_asia])
    svc.node_repository.list_by_ids = AsyncMock(return_value=[fallback_node])

    routes = [
        _make_route(uri=PRIMARY_URI, zone="europe", display="Europe"),
        _make_route(uri=PLAIN_URI, zone="asia", display="Asia"),
    ]
    out = await svc._render_subscription_payload(selected_routes=routes, client_id="cid")
    cfg = json.loads(out)
    tags = [o["tag"] for o in cfg["outbounds"]]
    # Europe → primary + fallback + urltest group;  Asia → plain extra outbound
    assert "Europe · primary" in tags
    assert "Europe · fallback" in tags
    assert "Europe" in tags
    assert "Asia" in tags
