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

DEFAULT_HAPP_COLOR_PROFILE = json.dumps(
    {
        "backgroundGradientRotationAngle": 180.0,
        "backgroundGradientColorIntensity": 1,
        "backgroundImageType": "light",
        "backgroundColors": [
            "#000000FF",
            "#030303FF",
            "#080605FF",
            "#0E0A08FF",
            "#16100CFF",
        ],
        "elipseColors": [
            "#FF4D00CC",
            "#FF6A1AAA",
            "#FF994480",
        ],
        "subsHeaderColor": "#0A0706FF",
        "subscriptionInfoBackgroundColor": "#0C0908FF",
        "subscriptionTrafficBackgroundColor": "#E05000FF",
        "subscriptionInfoTextColor": "#FFF0E4FF",
        "serverRowBackgroundColor": "#100C0AD4",
        "selectedServerRowColor": "#201410E8",
        "serverRowTitleTextColor": "#FFF4ECFF",
        "serverRowSubTitleTextColor": "#BFA898FF",
        "serverRowChevronColor": "#FF5500FF",
        "disclosureHeaderTextColor": "#FFF4ECFF",
        "disclosureSubHeaderTextColor": "#B09888FF",
        "buttonColor": "#FF5500FF",
        "buttonTextColor": "#FFFAF5FF",
        "buttonTimerColor": "#803000FF",
        "buttonImageType": "light",
        "powerIconColor": "#FFFAF5FF",
        "topBarButtonsColor": "#FFE4D0FF",
        "subHeaderButtonColor": "#FF5500FF",
        "additionalOptionsButtonColor": "#FFD0AAFF",
        "supportIconColor": "#FF5500FF",
        "profileWebPageIconColor": "#FF7733FF",
        "settingsControlsTintColor": "#FF5500FF",
    },
    separators=(",", ":"),
)
