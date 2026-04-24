from __future__ import annotations


TRANSPORT_SHORT: dict[str, str] = {
    "reality_tcp_v1": "reality",
    "ws_tls_v1": "wstls",
}


def transport_short_code(transport_profile_name: str) -> str:
    return TRANSPORT_SHORT.get(transport_profile_name, transport_profile_name)
