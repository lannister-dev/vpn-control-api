from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendCandidate:
    tag: str
    load: int
    tiebreak: int


def choose_backend_tag(
    candidates: list[BackendCandidate],
    *,
    current_tag: str | None,
) -> str | None:
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda c: (c.load, c.tiebreak, c.tag))
    best = ranked[0]
    if current_tag:
        current = next((c for c in ranked if c.tag == current_tag), None)
        if current is not None:
            gap = current.load - best.load
            relative = gap / max(1, current.load)
            if gap <= 2 or relative < 0.30:
                return current.tag
    return best.tag
