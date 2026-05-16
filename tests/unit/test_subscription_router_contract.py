from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from services.vpn.subscriptions.adapter import SubscriptionPublicAdapter
from services.vpn.subscriptions.exceptions import SubscriptionBuild, SubscriptionNotFound
from services.vpn.subscriptions.router import get_subscription_config


def _request_with_headers(headers: dict[str, str]):
    return SimpleNamespace(headers=headers)


def _adapter() -> SubscriptionPublicAdapter:
    return SubscriptionPublicAdapter(
        hwid_header="x-hwid",
        happ_profile_title="My VPN",
        happ_profile_update_interval_hours=24,
        happ_support_url="https://example.com/support",
        happ_profile_web_page_url="https://example.com/profile",
        happ_provider_id="provider-id-1",
        happ_routing="happ://routing/custom",
        happ_hide_settings=True,
        happ_always_hwid_enable=True,
        happ_color_profile='{"buttonColor":"#D96C3FFF","backgroundColors":["#07171EFF","#0D2A33FF"]}',
    )


@pytest.mark.asyncio
async def test_get_subscription_config_success_headers_and_payload():
    service = SimpleNamespace(
        build_payload=AsyncMock(return_value=("vless://one\nvless://two", "etag123", False, None))
    )
    request = _request_with_headers(
        {
            "if-none-match": "old-etag",
            "x-hwid": "hwid-1",
            "user-agent": "Happ/1.0",
        }
    )

    out = await get_subscription_config(
        token="tok",
        request=request,
        service=service,
        adapter=_adapter(),
    )

    assert out.status_code == 200
    body = out.body.decode()
    assert body == "vless://one\nvless://two"
    assert "#" not in body
    assert out.headers["etag"] == "etag123"
    assert out.headers["profile-title"].startswith("base64:")
    assert out.headers["profile-update-interval"] == "24"
    assert out.headers["support-url"] == "https://example.com/support"
    assert out.headers["profile-web-page-url"] == "https://example.com/profile"
    assert out.headers["providerid"] == "provider-id-1"
    assert out.headers["routing"] == "happ://routing/custom"
    assert out.headers["subscription-always-hwid-enable"] == "1"
    assert out.headers["color-profile"] == '{"buttonColor":"#D96C3FFF","backgroundColors":["#07171EFF","#0D2A33FF"]}'
    call = service.build_payload.await_args
    assert call is not None
    kwargs = call.kwargs
    assert kwargs["raw_token"] == "tok"
    assert kwargs["hwid"] == "hwid-1"
    assert kwargs["user_agent"] == "Happ/1.0"
    assert kwargs["if_none_match"] is None
    assert kwargs["extra_etag_signature"]
    assert len(kwargs["extra_etag_signature"]) == 12


@pytest.mark.asyncio
async def test_get_subscription_config_not_modified_returns_304():
    service = SimpleNamespace(
        build_payload=AsyncMock(return_value=("", "etag123", True, None))
    )
    request = _request_with_headers({"if-none-match": "etag123"})

    out = await get_subscription_config(
        token="tok",
        request=request,
        service=service,
        adapter=_adapter(),
    )

    assert out.status_code == 304
    assert out.headers["etag"] == "etag123"


@pytest.mark.asyncio
async def test_get_subscription_config_maps_not_found_error():
    service = SimpleNamespace(
        build_payload=AsyncMock(side_effect=SubscriptionNotFound())
    )
    request = _request_with_headers({})

    with pytest.raises(HTTPException) as exc:
        await get_subscription_config(
            token="tok",
            request=request,
            service=service,
            adapter=_adapter(),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Subscription not found"


@pytest.mark.asyncio
async def test_get_subscription_config_maps_build_unavailable_error():
    service = SimpleNamespace(
        build_payload=AsyncMock(side_effect=SubscriptionBuild("No available routes"))
    )
    request = _request_with_headers({})

    with pytest.raises(HTTPException) as exc:
        await get_subscription_config(
            token="tok",
            request=request,
            service=service,
            adapter=_adapter(),
        )

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_subscription_config_maps_sync_pending_error_to_503():
    service = SimpleNamespace(
        build_payload=AsyncMock(side_effect=SubscriptionBuild("Backend placement sync pending"))
    )
    request = _request_with_headers({})

    with pytest.raises(HTTPException) as exc:
        await get_subscription_config(
            token="tok",
            request=request,
            service=service,
            adapter=_adapter(),
        )

    assert exc.value.status_code == 503
