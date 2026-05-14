from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlsplit


@dataclass(slots=True)
class SingboxBuildError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(slots=True, frozen=True)
class ZoneOutbounds:
    tag: str
    primary_uri: str
    fallback_uri: str | None = None


_SELECTOR_TAG = "proxy"
_DIRECT_TAG = "direct"
_BLOCK_TAG = "block"
_DNS_OUT_TAG = "dns-out"


@dataclass(slots=True)
class SingboxConfig:
    grouped_zones: list[ZoneOutbounds] = field(default_factory=list)
    extra_outbounds: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        proxy_outbounds: list[dict] = []
        user_visible_tags: list[str] = []

        for zone in self.grouped_zones:
            if zone.fallback_uri:
                primary_tag = f"{zone.tag} · primary"
                fallback_tag = f"{zone.tag} · fallback"
                proxy_outbounds.append(_vless_uri_to_outbound(zone.primary_uri, tag=primary_tag))
                proxy_outbounds.append(_vless_uri_to_outbound(zone.fallback_uri, tag=fallback_tag))
                proxy_outbounds.append({
                    "type": "urltest",
                    "tag": zone.tag,
                    "outbounds": [primary_tag, fallback_tag],
                    "url": "https://www.gstatic.com/generate_204",
                    "interval": "30s",
                    "tolerance": 10000,
                    "interrupt_exist_connections": False,
                })
                user_visible_tags.append(zone.tag)
            else:
                proxy_outbounds.append(_vless_uri_to_outbound(zone.primary_uri, tag=zone.tag))
                user_visible_tags.append(zone.tag)

        for tag, uri in self.extra_outbounds:
            proxy_outbounds.append(_vless_uri_to_outbound(uri, tag=tag))
            user_visible_tags.append(tag)

        selector = {
            "type": "selector",
            "tag": _SELECTOR_TAG,
            "outbounds": user_visible_tags,
            "default": user_visible_tags[0] if user_visible_tags else None,
            "interrupt_exist_connections": True,
        }
        if selector["default"] is None:
            selector.pop("default")

        outbounds: list[dict] = [selector]
        outbounds.extend(proxy_outbounds)
        outbounds.append({"type": "direct", "tag": _DIRECT_TAG})
        outbounds.append({"type": "block", "tag": _BLOCK_TAG})
        outbounds.append({"type": "dns", "tag": _DNS_OUT_TAG})

        return {
            "log": {"level": "warn", "timestamp": True},
            "dns": {
                "servers": [
                    {"tag": "cf-dns", "address": "tls://1.1.1.1", "detour": _SELECTOR_TAG},
                    {"tag": "local", "address": "local", "detour": _DIRECT_TAG},
                ],
                "rules": [
                    {"outbound": "any", "server": "local"},
                ],
                "independent_cache": True,
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": "tun0",
                    "mtu": 9000,
                    "inet4_address": "172.19.0.1/30",
                    "auto_route": True,
                    "strict_route": True,
                    "stack": "mixed",
                    "sniff": True,
                },
            ],
            "outbounds": outbounds,
            "route": {
                "rules": [
                    {"protocol": "dns", "outbound": _DNS_OUT_TAG},
                    {"port": 53, "outbound": _DNS_OUT_TAG},
                    {"ip_is_private": True, "outbound": _DIRECT_TAG},
                ],
                "final": _SELECTOR_TAG,
                "auto_detect_interface": True,
                "override_android_vpn": True,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)


def _vless_uri_to_outbound(uri: str, *, tag: str) -> dict:
    if not uri.startswith("vless://"):
        raise SingboxBuildError(f"not a vless uri: {uri[:32]}…")

    parsed = urlsplit(uri)
    user = unquote(parsed.username or "")
    host = parsed.hostname or ""
    port = parsed.port or 0
    if not user or not host or not port:
        raise SingboxBuildError(f"vless uri missing uuid/host/port: {uri[:64]}…")

    raw_q = parse_qs(parsed.query, keep_blank_values=False)
    q: dict[str, str] = {k: v[0] for k, v in raw_q.items() if v}

    out: dict = {
        "type": "vless",
        "tag": tag,
        "server": host,
        "server_port": int(port),
        "uuid": user,
        "packet_encoding": "xudp",
    }

    flow = q.get("flow", "").strip()
    if flow:
        out["flow"] = flow

    transport = _transport_block(q)
    if transport:
        out["transport"] = transport

    tls = _tls_block(q)
    if tls:
        out["tls"] = tls

    return out


def _transport_block(q: dict[str, str]) -> dict | None:
    network = (q.get("type") or "tcp").lower()
    if network in ("tcp", "raw", ""):
        return None

    if network == "ws":
        transport: dict = {"type": "ws"}
        path = q.get("path")
        if path:
            transport["path"] = path
        host = q.get("host")
        if host:
            transport["headers"] = {"Host": host}
        return transport

    if network == "grpc":
        transport = {"type": "grpc"}
        svc = q.get("serviceName") or q.get("servicename")
        if svc:
            transport["service_name"] = svc
        return transport

    if network in ("http", "h2"):
        transport = {"type": "http"}
        path = q.get("path")
        if path:
            transport["path"] = path
        host = q.get("host")
        if host:
            transport["host"] = [host]
        return transport

    if network in ("httpupgrade", "xhttp"):
        transport = {"type": "httpupgrade"}
        path = q.get("path")
        if path:
            transport["path"] = path
        host = q.get("host")
        if host:
            transport["host"] = host
        return transport

    raise SingboxBuildError(f"unsupported transport type: {network}")


def _tls_block(q: dict[str, str]) -> dict | None:
    security = (q.get("security") or "").lower()
    if not security or security == "none":
        return None

    tls: dict = {"enabled": True}
    sni = q.get("sni") or q.get("peer")
    if sni:
        tls["server_name"] = sni

    alpn = q.get("alpn")
    if alpn:
        tls["alpn"] = [p for p in alpn.split(",") if p]

    fp = q.get("fp")
    if fp:
        tls["utls"] = {"enabled": True, "fingerprint": fp}

    if security == "reality":
        reality: dict = {"enabled": True}
        pbk = q.get("pbk")
        if pbk:
            reality["public_key"] = pbk
        sid = q.get("sid")
        if sid is not None:
            reality["short_id"] = sid
        tls["reality"] = reality

    return tls
