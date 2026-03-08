from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock


class InMemoryRateLimiter:
    """Simple sliding-window rate limiter keyed by IP address."""

    def __init__(self, max_attempts: int = 5, window_sec: int = 60):
        self._max = max_attempts
        self._window = window_sec
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            window = [t for t in self._attempts[key] if now - t < self._window]
            self._attempts[key] = window
            if len(window) >= self._max:
                return False
            window.append(now)
            return True

    def record(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._attempts[key].append(now)


login_rate_limiter = InMemoryRateLimiter(max_attempts=5, window_sec=60)
