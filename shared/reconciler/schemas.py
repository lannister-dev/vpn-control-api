from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconcilerStatus:
    name: str
    silence_sec: float
    max_silence_sec: float
    alive: bool
