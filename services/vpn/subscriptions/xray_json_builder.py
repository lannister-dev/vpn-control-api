from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlsplit


@dataclass(slots=True)
class XrayBuildError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(slots=True, frozen=True)
class ZoneOutbounds:
    tag: str
    primary_uri: str
    fallback_uri: str | None = None


_PROXY_TAG = "proxy"
_PROXY_FALLBACK_TAG = "proxy-2"
_DIRECT_TAG = "direct"
_BLOCK_TAG = "block"
_BALANCER_TAG = "balancer"


@dataclass(slots=True)
class XrayJsonConfig:
    grouped_zones: list[ZoneOutbounds] = field(default_factory=list)
    extra_outbounds: list[tuple[str, str]] = field(default_factory=list)

    def to_list(self) -> list[dict]:
        configs: list[dict] = []
        for zone in self.grouped_zones:
            configs.append(_build_zone_config(zone))
        for tag, uri in self.extra_outbounds:
            configs.append(_build_single_config(remarks=tag, uri=uri))
        return configs

    def to_json(self) -> str:
        return json.dumps(self.to_list(), separators=(",", ":"), ensure_ascii=False)


def _build_zone_config(zone: ZoneOutbounds) -> dict:
    if not zone.fallback_uri:
        return _build_single_config(remarks=zone.tag, uri=zone.primary_uri)

    primary = _vless_uri_to_outbound(zone.primary_uri, tag=_PROXY_TAG)
    fallback = _vless_uri_to_outbound(zone.fallback_uri, tag=_PROXY_FALLBACK_TAG)
    return {
        "remarks": zone.tag,
        "log": {"loglevel": "warning"},
        "dns": {"servers": ["1.1.1.1", "1.0.0.1"], "queryStrategy": "UseIP"},
        "outbounds": [
            primary,
            fallback,
            {"tag": _DIRECT_TAG, "protocol": "freedom"},
            {"tag": _BLOCK_TAG, "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "balancers": [
                {
                    "tag": _BALANCER_TAG,
                    "selector": [_PROXY_TAG],
                    "strategy": {"type": "leastPing"},
                }
            ],
            "rules": [
                {"type": "field", "protocol": ["bittorrent"], "outboundTag": _DIRECT_TAG},
                {"type": "field", "ip": ["geoip:private"], "outboundTag": _DIRECT_TAG},
                {"type": "field", "network": "tcp,udp", "balancerTag": _BALANCER_TAG},
            ],
        },
        "observatory": {
            "subjectSelector": [_PROXY_TAG],
            "probeUrl": "https://www.gstatic.com/generate_204",
            "probeInterval": "30s",
        },
    }


def _build_single_config(*, remarks: str, uri: str) -> dict:
    outbound = _vless_uri_to_outbound(uri, tag=_PROXY_TAG)
    return {
        "remarks": remarks,
        "log": {"loglevel": "warning"},
        "dns": {"servers": ["1.1.1.1", "1.0.0.1"], "queryStrategy": "UseIP"},
        "outbounds": [
            outbound,
            {"tag": _DIRECT_TAG, "protocol": "freedom"},
            {"tag": _BLOCK_TAG, "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "protocol": ["bittorrent"], "outboundTag": _DIRECT_TAG},
                {"type": "field", "ip": ["geoip:private"], "outboundTag": _DIRECT_TAG},
                {"type": "field", "network": "tcp,udp", "outboundTag": _PROXY_TAG},
            ],
        },
    }


def _vless_uri_to_outbound(uri: str, *, tag: str) -> dict:
    if not uri.startswith("vless://"):
        raise XrayBuildError(f"not a vless uri: {uri[:32]}…")

    parsed = urlsplit(uri)
    user = unquote(parsed.username or "")
    host = parsed.hostname or ""
    port = parsed.port or 0
    if not user or not host or not port:
        raise XrayBuildError(f"vless uri missing uuid/host/port: {uri[:64]}…")

    raw_q = parse_qs(parsed.query, keep_blank_values=False)
    q: dict[str, str] = {k: v[0] for k, v in raw_q.items() if v}

    flow = q.get("flow", "").strip()
    user_entry: dict = {"id": user, "encryption": "none"}
    if flow:
        user_entry["flow"] = flow

    settings = {
        "vnext": [
            {
                "address": host,
                "port": int(port),
                "users": [user_entry],
            }
        ]
    }

    return {
        "tag": tag,
        "protocol": "vless",
        "settings": settings,
        "streamSettings": _stream_settings(q),
    }


def _stream_settings(q: dict[str, str]) -> dict:
    network = (q.get("type") or "tcp").lower()
    if network == "raw":
        network = "tcp"

    stream: dict = {"network": network}

    if network == "ws":
        ws: dict = {}
        path = q.get("path")
        if path:
            ws["path"] = path
        host = q.get("host")
        if host:
            ws["headers"] = {"Host": host}
        if ws:
            stream["wsSettings"] = ws
    elif network == "grpc":
        grpc: dict = {}
        svc = q.get("serviceName") or q.get("servicename")
        if svc:
            grpc["serviceName"] = svc
        if grpc:
            stream["grpcSettings"] = grpc
    elif network in ("http", "h2"):
        http_settings: dict = {}
        path = q.get("path")
        if path:
            http_settings["path"] = path
        host = q.get("host")
        if host:
            http_settings["host"] = [host]
        stream["network"] = "h2"
        if http_settings:
            stream["httpSettings"] = http_settings
    elif network in ("httpupgrade", "xhttp"):
        stream["network"] = "httpupgrade"
        hu: dict = {}
        path = q.get("path")
        if path:
            hu["path"] = path
        host = q.get("host")
        if host:
            hu["host"] = host
        if hu:
            stream["httpupgradeSettings"] = hu

    security = (q.get("security") or "").lower()
    if security == "tls":
        stream["security"] = "tls"
        stream["tlsSettings"] = _tls_settings(q)
    elif security == "reality":
        stream["security"] = "reality"
        stream["realitySettings"] = _reality_settings(q)

    return stream


def _tls_settings(q: dict[str, str]) -> dict:
    settings: dict = {}
    sni = q.get("sni") or q.get("peer")
    if sni:
        settings["serverName"] = sni
    alpn = q.get("alpn")
    if alpn:
        settings["alpn"] = [p for p in alpn.split(",") if p]
    fp = q.get("fp")
    if fp:
        settings["fingerprint"] = fp
    return settings


def _reality_settings(q: dict[str, str]) -> dict:
    settings: dict = {}
    sni = q.get("sni") or q.get("peer")
    if sni:
        settings["serverName"] = sni
    fp = q.get("fp")
    if fp:
        settings["fingerprint"] = fp
    pbk = q.get("pbk")
    if pbk:
        settings["publicKey"] = pbk
    sid = q.get("sid")
    if sid is not None:
        settings["shortId"] = sid
    spx = q.get("spx")
    if spx:
        settings["spiderX"] = spx
    return settings
