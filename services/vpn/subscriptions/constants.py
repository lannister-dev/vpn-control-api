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
        "backgroundGradientRotationAngle": 32.0,
        "backgroundGradientColorIntensity": 1,
        "backgroundImageType": "light",
        "backgroundColors": [
            "#07171EFF",
            "#0D2A33FF",
            "#123F4AFF",
            "#1D6A73FF",
            "#7FDBD4FF",
        ],
        "elipseColors": [
            "#D96C3FFF",
            "#8CF3E8CC",
            "#F4C95DCC",
        ],
        "subsHeaderColor": "#103741FF",
        "subscriptionInfoBackgroundColor": "#0A242CFF",
        "subscriptionTrafficBackgroundColor": "#C96A3DFF",
        "subscriptionInfoTextColor": "#F4FBFAFF",
        "serverRowBackgroundColor": "#13353ECC",
        "selectedServerRowColor": "#1E5663E6",
        "serverRowTitleTextColor": "#F3FCFBFF",
        "serverRowSubTitleTextColor": "#B7D7D4FF",
        "serverRowChevronColor": "#F4C95DFF",
        "disclosureHeaderTextColor": "#F4FBFAFF",
        "disclosureSubHeaderTextColor": "#9FC3C0FF",
        "buttonColor": "#D96C3FFF",
        "buttonTextColor": "#FFF8F4FF",
        "buttonTimerColor": "#FFF8F4FF",
        "buttonImageType": "light",
        "powerIconColor": "#0E3139FF",
        "topBarButtonsColor": "#F3FCFBFF",
        "subHeaderButtonColor": "#F4C95DFF",
        "additionalOptionsButtonColor": "#F4FBFAFF",
        "supportIconColor": "#F4C95DFF",
        "profileWebPageIconColor": "#8CF3E8FF",
        "settingsControlsTintColor": "#7FDBD4FF",
    },
    separators=(",", ":"),
)
