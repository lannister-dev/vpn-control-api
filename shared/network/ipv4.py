"""Force IPv4 for all outgoing connections.

Kubernetes clusters without IPv6 connectivity fail when external services
(e.g. oauth.telegram.org) return AAAA DNS records — Python tries IPv6 first
and gets ``[Errno 101] Network is unreachable``.

Usage — call once at process startup, before any network I/O::

    from shared.network.ipv4 import force_ipv4
    force_ipv4()
"""

from __future__ import annotations

import socket

_patched = False


def force_ipv4():
    global _patched
    if _patched:
        return
    _orig_getaddrinfo = socket.getaddrinfo

    def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        if family == socket.AF_UNSPEC:
            family = socket.AF_INET
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _ipv4_only
    _patched = True
