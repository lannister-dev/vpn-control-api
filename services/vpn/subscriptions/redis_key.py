from __future__ import annotations

import hashlib

_SUB_RATE_LIMIT_PREFIX = "sub:rl"
_SUB_PAYLOAD_CACHE_PREFIX = "sub:cfg"
_SUB_PAYLOAD_CACHE_INDEX_PREFIX = "sub:cfg:index"
_SUB_PAYLOAD_LOCK_PREFIX = "sub:cfg:lock"


def rate_limit(token_hash: str) -> str:
    return f"{_SUB_RATE_LIMIT_PREFIX}:{token_hash}"


def payload_cache(*, token_hash: str, hwid: str | None) -> str:
    return f"{_SUB_PAYLOAD_CACHE_PREFIX}:{token_hash}:{_hwid_marker(hwid)}"


def payload_cache_index(*, token_hash: str) -> str:
    return f"{_SUB_PAYLOAD_CACHE_INDEX_PREFIX}:{token_hash}"


def payload_build_lock(*, token_hash: str, hwid: str | None) -> str:
    return f"{_SUB_PAYLOAD_LOCK_PREFIX}:{token_hash}:{_hwid_marker(hwid)}"


def is_payload_cache_key(value: str) -> bool:
    return value.startswith(f"{_SUB_PAYLOAD_CACHE_PREFIX}:")


def _hwid_marker(hwid: str | None) -> str:
    if hwid is None:
        return "none"
    normalized = hwid.strip()
    if not normalized:
        return "empty"
    return hashlib.sha256(normalized.encode()).hexdigest()
