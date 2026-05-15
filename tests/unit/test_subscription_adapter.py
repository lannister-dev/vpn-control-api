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
        happ_hide_settings=True,
        happ_always_hwid_enable=True,
        happ_color_profile='{"buttonColor":"#D96C3FFF","backgroundColors":["#07171EFF","#0D2A33FF"]}',
    )


def test_build_success_response_contains_contract_fields():
    response = _adapter().build_success_response(
        etag="abc123",
        payload="vless://a\n\nvless://b",
        not_modified=False,
        user_agent="Happ/1.0",
    )

    assert response.metric_result == "success"
    assert response.status_code == 200
    assert response.headers["ETag"] == "abc123"
    assert response.headers["profile-title"] == "My VPN"
    assert response.headers["profile-update-interval"] == "24"
    assert response.headers["support-url"] == "https://example.com/support"
    assert response.headers["profile-web-page-url"] == "https://example.com/profile"
    assert response.headers["providerid"] == "provider-id-1"
    assert response.headers["routing"] == "happ://routing/custom"
    assert response.headers["subscription-always-hwid-enable"] == "1"
    assert response.headers["color-profile"] == '{"buttonColor":"#D96C3FFF","backgroundColors":["#07171EFF","#0D2A33FF"]}'
    assert response.payload.endswith("vless://a\n\nvless://b")
    assert "#hide-settings: 1" in response.payload
    assert "#subscription-always-hwid-enable: 1" in response.payload
    assert "#profile-title: My VPN" in response.payload
    assert "#profile-update-interval: 24" in response.payload
    assert "#providerid: provider-id-1" in response.payload
    assert "#color-profile:" in response.payload
    assert response.headers["Vary"] == "If-None-Match, User-Agent, x-hwid"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"


def test_build_success_response_not_modified_has_no_payload():
    response = _adapter().build_success_response(
        etag="abc123",
        payload="",
        not_modified=True,
        user_agent="Happ/1.0",
    )

    assert response.metric_result == "not_modified"
    assert response.status_code == 304
    assert response.payload is None


def test_should_disable_not_modified_when_directives_configured_regardless_of_ua():
    adapter = _adapter()
    assert adapter.should_disable_not_modified(user_agent="Happ/1.0") is True
    assert adapter.should_disable_not_modified(user_agent="HappVPN-macOS") is True
    assert adapter.should_disable_not_modified(user_agent="OtherClient/1.0") is True
    assert adapter.should_disable_not_modified(user_agent=None) is True


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
