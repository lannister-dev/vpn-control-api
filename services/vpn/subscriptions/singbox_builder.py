"""Sing-box client config generator for Happ subscriptions.

Translates `vless://...` URIs into sing-box outbound dicts and bundles a
primary + fallback pair into an `urltest` group so the Happ client transparently
fails over (e.g. DPI-blocked primary → whitelist entry).

The whole module is pure: no DB, no I/O, no globals — easy to unit-test.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlsplit

# ── value objects ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class SingboxBuildError(Exception):
    """Raised when a URI cannot be translated to a sing-box outbound."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(slots=True, frozen=True)
class ZoneOutbounds:
    """A user-visible zone in the Happ UI and its primary + optional fallback.

    `tag` is what the user sees ("Europe"). `primary_uri` must be present;
    `fallback_uri` is optional — when set, the two are wrapped in an `urltest`
    group with high tolerance (always prefer primary unless dead).
    """

    tag: str
    primary_uri: str
    fallback_uri: str | None = None


@dataclass(slots=True)
class SingboxConfig:
    """Sing-box client config: outbounds + a minimal `route`.

    `extra_outbounds` is a list of plain vless outbounds (without fallback)
    that should appear as-is.
    """

    grouped_zones: list[ZoneOutbounds] = field(default_factory=list)
    extra_outbounds: list[tuple[str, str]] = field(default_factory=list)  # (tag, uri)

    def to_dict(self) -> dict:
        outbounds: list[dict] = []

        for zone in self.grouped_zones:
            primary_tag = f"{zone.tag} · primary"
            outbounds.append(_vless_uri_to_outbound(zone.primary_uri, tag=primary_tag))
            if zone.fallback_uri:
                fallback_tag = f"{zone.tag} · fallback"
                outbounds.append(_vless_uri_to_outbound(zone.fallback_uri, tag=fallback_tag))
                outbounds.append({
                    "type": "urltest",
                    "tag": zone.tag,
                    "outbounds": [primary_tag, fallback_tag],
                    "url": "https://www.gstatic.com/generate_204",
                    "interval": "30s",
                    # Very high tolerance: only switch when the primary actually fails.
                    # If both respond, keep the first one (which is the primary).
                    "tolerance": 10000,
                    "interrupt_exist_connections": False,
                })
            # If no fallback — primary itself acts as the user-visible outbound.
            # Rename it to the zone tag for a clean Happ UI.
            else:
                outbounds[-1]["tag"] = zone.tag

        for tag, uri in self.extra_outbounds:
            outbounds.append(_vless_uri_to_outbound(uri, tag=tag))

        outbounds.append({"type": "direct", "tag": "direct"})
        outbounds.append({"type": "block", "tag": "block"})

        return {"outbounds": outbounds}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)


# ── URI → outbound translation ──────────────────────────────────────────────


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
