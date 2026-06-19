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
    "backgroundGradientRotationAngle": 160.0,
    "backgroundGradientColorIntensity": 0.35,
    "backgroundImageType": "dark",
    "backgroundColors": [
        "#0E0D0CFF",
        "#131110FF",
        "#1A1816FF",
        "#0F0E0DFF",
    ],
    "elipseColors": [
        "#FF6B1A33",
        "#E35E1A1C",
        "#0E0D0C00",
    ],
    "subsHeaderColor": "#131110FF",
    "subscriptionInfoBackgroundColor": "#1A1816CC",
    "subscriptionTrafficBackgroundColor": "#D2581CFF",
    "subscriptionInfoTextColor": "#C9C6C0FF",
    "serverRowBackgroundColor": "#1A1816CC",
    "selectedServerRowColor": "#E35E1A2E",
    "serverRowTitleTextColor": "#F3F1ECFF",
    "serverRowSubTitleTextColor": "#9A968FFF",
    "serverRowChevronColor": "#615D57FF",
    "disclosureHeaderTextColor": "#F3F1ECFF",
    "disclosureSubHeaderTextColor": "#9A968FFF",
    "buttonColor": "#E35E1AFF",
    "buttonTextColor": "#FFF6EFFF",
    "buttonTimerColor": "#FFD8C0FF",
    "buttonImageType": "dark",
    "powerIconColor": "#FFF6EFFF",
    "topBarButtonsColor": "#D7D4CFFF",
    "subHeaderButtonColor": "#F2691FFF",
    "additionalOptionsButtonColor": "#B6B2ACFF",
    "supportIconColor": "#FF7A2EFF",
    "profileWebPageIconColor": "#9A968FFF",
    "settingsControlsTintColor": "#FF6B1AFF",
}

HAPP_COLOR_PROFILE_GRAPHITE = {
    "backgroundGradientRotationAngle": 160.0,
    "backgroundGradientColorIntensity": 0.3,
    "backgroundImageType": "dark",
    "backgroundColors": [
        "#0E0D0CFF",
        "#121110FF",
        "#171513FF",
        "#0E0D0CFF",
    ],
    "elipseColors": [
        "#FF6B1A1F",
        "#A850241A",
        "#0E0D0C00",
    ],
    "subsHeaderColor": "#121110FF",
    "subscriptionInfoBackgroundColor": "#17151399",
    "subscriptionTrafficBackgroundColor": "#A85024FF",
    "subscriptionInfoTextColor": "#C4C1BBFF",
    "serverRowBackgroundColor": "#17151399",
    "selectedServerRowColor": "#2A2724FF",
    "serverRowTitleTextColor": "#EEECE7FF",
    "serverRowSubTitleTextColor": "#928E86FF",
    "serverRowChevronColor": "#5C5853FF",
    "disclosureHeaderTextColor": "#EEECE7FF",
    "disclosureSubHeaderTextColor": "#928E86FF",
    "buttonColor": "#211F1CFF",
    "buttonTextColor": "#ECEAE6FF",
    "buttonTimerColor": "#8C887FFF",
    "buttonImageType": "dark",
    "powerIconColor": "#FF6B1AFF",
    "topBarButtonsColor": "#CFCCC6FF",
    "subHeaderButtonColor": "#C9C5BEFF",
    "additionalOptionsButtonColor": "#B0ACA5FF",
    "supportIconColor": "#E0762FFF",
    "profileWebPageIconColor": "#928E86FF",
    "settingsControlsTintColor": "#FF6B1AFF",
}

HAPP_COLOR_PROFILE_GRAPHITE_JSON = json.dumps(HAPP_COLOR_PROFILE_GRAPHITE, separators=(",", ":"))

DEFAULT_HAPP_COLOR_PROFILE = json.dumps(HAPP_COLOR_PROFILE_EMBER, separators=(",", ":"))
