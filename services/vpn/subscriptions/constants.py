import json

from services.vpn.keys.schemas import VpnTransport

WHITELIST_SUFFIX = " | WL"
WHITELIST_SERVER_DESCRIPTION = "🔓 глушилки"

RATE_LIMIT_REQUESTS = 300
RATE_LIMIT_WINDOW_SEC = 3600
DEFAULT_ROTATION_GRACE_SEC = 3600
PAYLOAD_BUILD_LOCK_TTL_SEC = 5
PAYLOAD_BUILD_WAIT_ATTEMPTS = 2
PAYLOAD_BUILD_WAIT_DELAY_SEC = 0.05

TRANSPORT_PRIORITY: dict[str, int] = {
    VpnTransport.reality.value: 0,
    VpnTransport.ws.value: 1,
    VpnTransport.xhttp.value: 2,
    VpnTransport.tcp.value: 3,
}

DEFAULT_SUBSCRIPTION_TRANSPORT_BUNDLE: tuple[VpnTransport, ...] = (
    VpnTransport.reality,
    VpnTransport.ws,
)

HAPP_COLOR_PROFILE_EMBER = {
    "backgroundGradientRotationAngle": 180.0,
    "backgroundGradientColorIntensity": 0.6,
    "backgroundImageType": "dark",
    "backgroundColors": [
        "#0B0A09FF",
        "#13110FFF",
        "#1A1614FF",
        "#0C0B0AFF",
    ],
    "elipseColors": [
        "#FF6B1A4D",
        "#E0501033",
        "#00000000",
    ],
    "subsHeaderColor": "#0C0B0AFF",
    "subscriptionInfoBackgroundColor": "#14110FCC",
    "subscriptionTrafficBackgroundColor": "#F0601EFF",
    "subscriptionInfoTextColor": "#CBCBCFFF",
    "serverRowBackgroundColor": "#14110FCC",
    "selectedServerRowColor": "#FF6B1A26",
    "serverRowTitleTextColor": "#F1F1F2FF",
    "serverRowSubTitleTextColor": "#9A9B9FFF",
    "serverRowChevronColor": "#6C6D71FF",
    "disclosureHeaderTextColor": "#F1F1F2FF",
    "disclosureSubHeaderTextColor": "#9A9B9FFF",
    "buttonColor": "#F0601EFF",
    "buttonTextColor": "#FFFFFFFF",
    "buttonTimerColor": "#FFCBA6FF",
    "buttonImageType": "dark",
    "powerIconColor": "#FFFFFFFF",
    "topBarButtonsColor": "#CFCFD3FF",
    "subHeaderButtonColor": "#FF6B1AFF",
    "additionalOptionsButtonColor": "#AFAFB4FF",
    "supportIconColor": "#FF7A2EFF",
    "profileWebPageIconColor": "#9A9B9FFF",
    "settingsControlsTintColor": "#FF6B1AFF",
}

HAPP_COLOR_PROFILE_GRAPHITE = {
    "backgroundGradientRotationAngle": 180.0,
    "backgroundGradientColorIntensity": 0.5,
    "backgroundImageType": "dark",
    "backgroundColors": [
        "#0A0A09FF",
        "#111010FF",
        "#161413FF",
        "#0B0B0AFF",
    ],
    "elipseColors": [
        "#FF6B1A2E",
        "#4A474422",
        "#00000000",
    ],
    "subsHeaderColor": "#0B0A0AFF",
    "subscriptionInfoBackgroundColor": "#141211B3",
    "subscriptionTrafficBackgroundColor": "#C2551EFF",
    "subscriptionInfoTextColor": "#C4C4C8FF",
    "serverRowBackgroundColor": "#141211B3",
    "selectedServerRowColor": "#242220FF",
    "serverRowTitleTextColor": "#ECECEEFF",
    "serverRowSubTitleTextColor": "#94959AFF",
    "serverRowChevronColor": "#5E5F63FF",
    "disclosureHeaderTextColor": "#ECECEEFF",
    "disclosureSubHeaderTextColor": "#94959AFF",
    "buttonColor": "#1B1917FF",
    "buttonTextColor": "#E9E9EBFF",
    "buttonTimerColor": "#8A8A8EFF",
    "buttonImageType": "dark",
    "powerIconColor": "#FF6B1AFF",
    "topBarButtonsColor": "#CBCBCFFF",
    "subHeaderButtonColor": "#C7C7CBFF",
    "additionalOptionsButtonColor": "#ACACB1FF",
    "supportIconColor": "#E0762FFF",
    "profileWebPageIconColor": "#94959AFF",
    "settingsControlsTintColor": "#FF6B1AFF",
}

HAPP_COLOR_PROFILE_GRAPHITE_JSON = json.dumps(HAPP_COLOR_PROFILE_GRAPHITE, separators=(",", ":"))

DEFAULT_HAPP_COLOR_PROFILE = json.dumps(HAPP_COLOR_PROFILE_EMBER, separators=(",", ":"))
