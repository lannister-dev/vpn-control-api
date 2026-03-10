from __future__ import annotations

from datetime import datetime, timezone
import secrets


def identity_accepts_token(identity, token_hash: str, *, now: datetime | None = None) -> bool:
    if secrets.compare_digest(identity.auth_token_hash, token_hash):
        return True

    prev_hash = getattr(identity, "prev_auth_token_hash", None)
    if not prev_hash or not secrets.compare_digest(prev_hash, token_hash):
        return False

    valid_until = getattr(identity, "prev_auth_token_valid_until", None)
    if valid_until is None:
        return False

    current_time = now or datetime.now(timezone.utc)
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    else:
        valid_until = valid_until.astimezone(timezone.utc)
    return valid_until >= current_time
