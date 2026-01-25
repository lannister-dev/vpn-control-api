VPN_PROFILES_RAW = {
    "ws_tls_v1": {
        "type": "ws_tls",
        "version": 1,
        "client": {
            "path": "/ws",
            "host": "cdn.example.com",
            "sni": "cdn.example.com",
        },
        "metadata": {
            "display_name": "WebSocket + TLS",
            "region_support": ["de", "nl", "fi"],
        },
    },
    "reality_tcp_v1": {
        "type": "reality_tcp",
        "version": 1,
        "client": {
            "sni": "www.cloudflare.com",
            "flow": "xtls-rprx-vision",
            "fingerprint": "chrome",
            "public_key": "PUBLIC_KEY",
            "short_id": "abcd1234",
        },
        "metadata": {
            "display_name": "REALITY + TCP",
            "region_support": ["de", "nl"],
        },
    },
}
