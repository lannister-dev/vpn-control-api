from services.vpn.subscriptions.adapter import SubscriptionPublicAdapter
from services.vpn.subscriptions.exceptions import (
    SubscriptionBuild,
    SubscriptionHwidRequired,
    SubscriptionNotFound,
)


def _adapter() -> SubscriptionPublicAdapter:
    return SubscriptionPublicAdapter(
        hwid_header="x-hwid",
        happ_profile_title="My VPN",
        happ_profile_update_interval_hours=24,
        happ_support_url="https://example.com/support",
        happ_profile_web_page_url="https://example.com/profile",
        happ_provider_id="provider-id-1",
        happ_routing="happ://routing/custom",
        happ_color_profile='{"buttonColor":"#D96C3FFF","backgroundColors":["#07171EFF","#0D2A33FF"]}',
    )


def test_build_success_response_contains_contract_fields():
    response = _adapter().build_success_response(
        etag="abc123",
        payload="vless://a\n\nvless://b",
        not_modified=False,
    )

    assert response.metric_result == "success"
    assert response.status_code == 200
    assert response.payload == "vless://a\n\nvless://b"
    assert response.headers["ETag"] == "abc123"
    assert response.headers["profile-title"] == "My VPN"
    assert response.headers["profile-update-interval"] == "24"
    assert response.headers["support-url"] == "https://example.com/support"
    assert response.headers["profile-web-page-url"] == "https://example.com/profile"
    assert response.headers["providerid"] == "provider-id-1"
    assert response.headers["routing"] == "happ://routing/custom"
    assert response.headers["color-profile"] == '{"buttonColor":"#D96C3FFF","backgroundColors":["#07171EFF","#0D2A33FF"]}'
    assert response.headers["Vary"] == "If-None-Match, User-Agent, x-hwid"


def test_build_success_response_not_modified_has_no_payload():
    response = _adapter().build_success_response(
        etag="abc123",
        payload="",
        not_modified=True,
    )

    assert response.metric_result == "not_modified"
    assert response.status_code == 304
    assert response.payload is None


def test_map_subscription_error_not_found():
    mapped = _adapter().map_error(SubscriptionNotFound())
    assert mapped.metric_result == "not_found"
    assert mapped.status_code == 404


def test_map_subscription_error_hwid_required_keeps_opaque_response():
    mapped = _adapter().map_error(SubscriptionHwidRequired())
    assert mapped.metric_result == "hwid_required"
    assert mapped.status_code == 404


def test_map_subscription_error_build_no_available_is_503():
    mapped = _adapter().map_error(SubscriptionBuild("No available routes"))
    assert mapped.metric_result == "build_error"
    assert mapped.status_code == 503


def test_map_subscription_error_build_sync_pending_is_503():
    mapped = _adapter().map_error(SubscriptionBuild("Backend placement sync pending"))
    assert mapped.metric_result == "build_error"
    assert mapped.status_code == 503
