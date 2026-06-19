WS_TLS_DEFAULT_PATH = "/api/v1/stream"

XHTTP_DEFAULT_PATH = "/v1/edge"
XHTTP_DEFAULT_MODE = "packet-up"
XHTTP_DEFAULT_UPLINK_METHOD = "GET"
XHTTP_DEFAULT_ALPN = "h2,http/1.1"
XHTTP_DEFAULT_EXTRA = {
    "uplinkHTTPMethod": "GET",
    "xPaddingKey": "_dc",
    "xPaddingHeader": "X-Client-Version",
    "xPaddingMethod": "tokenish",
    "xPaddingObfsMode": True,
    "xPaddingPlacement": "queryInHeader",
}
