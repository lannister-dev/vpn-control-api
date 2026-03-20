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
