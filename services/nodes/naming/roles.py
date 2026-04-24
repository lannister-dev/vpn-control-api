from __future__ import annotations

from services.nodes.constants import (
    ROLE_BACKEND,
    ROLE_ENTRY,
    ROLE_WHITELIST_ENTRY,
)


SHORT_TO_ROLE: dict[str, str] = {
    "entry": ROLE_ENTRY,
    "wl": ROLE_WHITELIST_ENTRY,
    "be": ROLE_BACKEND,
}
