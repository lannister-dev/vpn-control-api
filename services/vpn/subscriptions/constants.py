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
#
# HAPP_COLOR_PROFILE_EMBER = {
#     "backgroundGradientRotationAngle": 180.0,
#     "backgroundGradientColorIntensity": 0.5,
#     "backgroundImageType": "dark",
#     "backgroundColors": [
#         "#0A0B0DFF",
#         "#101116FF",
#         "#16171CFF",
#         "#0C0D10FF",
#     ],
#     "elipseColors": [
#         "#FF6B1A45",
#         "#FF6B1A22",
#         "#0A0B0D00",
#     ],
#     "subsHeaderColor": "#0C0D10FF",
#     "subscriptionInfoBackgroundColor": "#15161BCC",
#     "subscriptionTrafficBackgroundColor": "#FF6B1AFF",
#     "subscriptionInfoTextColor": "#C7C9CFFF",
#     "serverRowBackgroundColor": "#15161BCC",
#     "selectedServerRowColor": "#FF6B1A26",
#     "serverRowTitleTextColor": "#F3F4F6FF",
#     "serverRowSubTitleTextColor": "#9A9CA4FF",
#     "serverRowChevronColor": "#62646CFF",
#     "disclosureHeaderTextColor": "#F3F4F6FF",
#     "disclosureSubHeaderTextColor": "#9A9CA4FF",
#     "buttonColor": "#FF6B1AFF",
#     "buttonTextColor": "#FFFFFFFF",
#     "buttonTimerColor": "#FFC9A4FF",
#     "buttonImageType": "dark",
#     "powerIconColor": "#FFFFFFFF",
#     "topBarButtonsColor": "#CBCDD3FF",
#     "subHeaderButtonColor": "#FF7A30FF",
#     "additionalOptionsButtonColor": "#AEB0B7FF",
#     "supportIconColor": "#FF7A30FF",
#     "profileWebPageIconColor": "#9A9CA4FF",
#     "settingsControlsTintColor": "#FF6B1AFF",
# }
#
# HAPP_COLOR_PROFILE_GRAPHITE = {
#     "backgroundGradientRotationAngle": 180.0,
#     "backgroundGradientColorIntensity": 0.45,
#     "backgroundImageType": "dark",
#     "backgroundColors": [
#         "#0A0B0DFF",
#         "#0F1014FF",
#         "#141519FF",
#         "#0B0C0FFF",
#     ],
#     "elipseColors": [
#         "#FF6B1A2A",
#         "#3A3C4422",
#         "#0A0B0D00",
#     ],
#     "subsHeaderColor": "#0B0C0FFF",
#     "subscriptionInfoBackgroundColor": "#14151AB3",
#     "subscriptionTrafficBackgroundColor": "#C2551EFF",
#     "subscriptionInfoTextColor": "#C2C4CAFF",
#     "serverRowBackgroundColor": "#14151AB3",
#     "selectedServerRowColor": "#212329FF",
#     "serverRowTitleTextColor": "#ECEDEFFF",
#     "serverRowSubTitleTextColor": "#9698A0FF",
#     "serverRowChevronColor": "#5C5E66FF",
#     "disclosureHeaderTextColor": "#ECEDEFFF",
#     "disclosureSubHeaderTextColor": "#9698A0FF",
#     "buttonColor": "#191A1FFF",
#     "buttonTextColor": "#E8E9ECFF",
#     "buttonTimerColor": "#85878EFF",
#     "buttonImageType": "dark",
#     "powerIconColor": "#FF6B1AFF",
#     "topBarButtonsColor": "#C8CAD0FF",
#     "subHeaderButtonColor": "#C4C6CCFF",
#     "additionalOptionsButtonColor": "#AAACB3FF",
#     "supportIconColor": "#E0762FFF",
#     "profileWebPageIconColor": "#9698A0FF",
#     "settingsControlsTintColor": "#FF6B1AFF",
# }
#
# HAPP_COLOR_PROFILE_GRAPHITE_JSON = json.dumps(HAPP_COLOR_PROFILE_GRAPHITE, separators=(",", ":"))
#
# DEFAULT_HAPP_COLOR_PROFILE = json.dumps(HAPP_COLOR_PROFILE_EMBER, separators=(",", ":"))
