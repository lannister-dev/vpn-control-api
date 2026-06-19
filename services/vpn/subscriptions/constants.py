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

HAPP_COLOR_PROFILE_DARK_PREMIUM = {
    "backgroundGradientRotationAngle": 135.0,
    "backgroundGradientColorIntensity": 0.55,
    "backgroundImageType": "dark",
    "backgroundColors": [
        "#100E0AFF",
        "#17150FFF",
        "#1F1A12FF",
        "#13100BFF",
    ],
    "elipseColors": [
        "#D9531A40",
        "#6E2C1233",
        "#17150F00",
    ],
    "subsHeaderColor": "#ECE3D4FF",
    "subscriptionInfoBackgroundColor": "#1C180FCC",
    "subscriptionTrafficBackgroundColor": "#2A2317CC",
    "subscriptionInfoTextColor": "#D8CFBFFF",
    "serverRowBackgroundColor": "#1C180FCC",
    "selectedServerRowColor": "#D9531A33",
    "serverRowTitleTextColor": "#ECE3D4FF",
    "serverRowSubTitleTextColor": "#8E8678FF",
    "serverRowChevronColor": "#6E665BFF",
    "disclosureHeaderTextColor": "#ECE3D4FF",
    "disclosureSubHeaderTextColor": "#9A9286FF",
    "buttonColor": "#C24F1AFF",
    "buttonTextColor": "#FBF3E6FF",
    "buttonTimerColor": "#ECE3D4FF",
    "buttonImageType": "dark",
    "powerIconColor": "#FBF3E6FF",
    "topBarButtonsColor": "#ECE3D4FF",
    "subHeaderButtonColor": "#E8631EFF",
    "additionalOptionsButtonColor": "#C9BFAEFF",
    "supportIconColor": "#FF6B1AFF",
    "profileWebPageIconColor": "#A89F90FF",
    "settingsControlsTintColor": "#E8631EFF",
}

HAPP_COLOR_PROFILE_SOFT = {
    "backgroundGradientRotationAngle": 120.0,
    "backgroundGradientColorIntensity": 0.4,
    "backgroundImageType": "dark",
    "backgroundColors": [
        "#121009FF",
        "#18150EFF",
        "#1C180FFF",
        "#0F0D08FF",
    ],
    "elipseColors": [
        "#A8481C2E",
        "#6E2C1226",
        "#14110B00",
    ],
    "subsHeaderColor": "#E4DACAFF",
    "subscriptionInfoBackgroundColor": "#19150DCC",
    "subscriptionTrafficBackgroundColor": "#241E14CC",
    "subscriptionInfoTextColor": "#CFC6B6FF",
    "serverRowBackgroundColor": "#19150DCC",
    "selectedServerRowColor": "#A8481C26",
    "serverRowTitleTextColor": "#E4DACAFF",
    "serverRowSubTitleTextColor": "#857D70FF",
    "serverRowChevronColor": "#655E54FF",
    "disclosureHeaderTextColor": "#E4DACAFF",
    "disclosureSubHeaderTextColor": "#938B7EFF",
    "buttonColor": "#A8481CFF",
    "buttonTextColor": "#F5EEDFFF",
    "buttonTimerColor": "#D8CFBFFF",
    "buttonImageType": "dark",
    "powerIconColor": "#F5EEDFFF",
    "topBarButtonsColor": "#E4DACAFF",
    "subHeaderButtonColor": "#C9BFAEFF",
    "additionalOptionsButtonColor": "#BBB1A1FF",
    "supportIconColor": "#BD5524FF",
    "profileWebPageIconColor": "#9A9286FF",
    "settingsControlsTintColor": "#B5552AFF",
}

HAPP_COLOR_PROFILE_SOFT_JSON = json.dumps(HAPP_COLOR_PROFILE_SOFT, separators=(",", ":"))

DEFAULT_HAPP_COLOR_PROFILE = json.dumps(HAPP_COLOR_PROFILE_DARK_PREMIUM, separators=(",", ":"))
