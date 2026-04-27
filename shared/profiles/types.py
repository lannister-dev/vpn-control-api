from __future__ import annotations

from enum import Enum


class ProfileType(str, Enum):
    ws_tls = "ws_tls"
    reality_tcp = "reality_tcp"