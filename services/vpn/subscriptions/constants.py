import json

from services.vpn.keys.schemas import VpnTransport


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

DEFAULT_HAPP_COLOR_PROFILE = json.dumps(
    {
        "backgroundGradientRotationAngle": 24.0,
        "backgroundGradientColorIntensity": 1,
        "backgroundImageType": "light",
        "backgroundColors": [
            "#050505FF",
            "#0D0D0EFF",
            "#161313FF",
            "#221915FF",
            "#35241BFF",
        ],
        "elipseColors": [
            "#FF6A1ACC",
            "#E7A15CCC",
            "#FFF0D1A6",
        ],
        "subsHeaderColor": "#16100EFF",
        "subscriptionInfoBackgroundColor": "#120F0DFF",
        "subscriptionTrafficBackgroundColor": "#8E5C35FF",
        "subscriptionInfoTextColor": "#FFF5EAFF",
        "serverRowBackgroundColor": "#171210D4",
        "selectedServerRowColor": "#2A201AE8",
        "serverRowTitleTextColor": "#FFF6ECFF",
        "serverRowSubTitleTextColor": "#D4C2B3FF",
        "serverRowChevronColor": "#E6A15BFF",
        "disclosureHeaderTextColor": "#FFF6ECFF",
        "disclosureSubHeaderTextColor": "#C6B3A3FF",
        "buttonColor": "#F3E5D7FF",
        "buttonTextColor": "#1B1511FF",
        "buttonTimerColor": "#4D3727FF",
        "buttonImageType": "dark",
        "powerIconColor": "#1B1511FF",
        "topBarButtonsColor": "#FFF0E1FF",
        "subHeaderButtonColor": "#E6A15BFF",
        "additionalOptionsButtonColor": "#EADFD2FF",
        "supportIconColor": "#E6A15BFF",
        "profileWebPageIconColor": "#F0C28BFF",
        "settingsControlsTintColor": "#E6A15BFF",
    },
    separators=(",", ":"),
)
