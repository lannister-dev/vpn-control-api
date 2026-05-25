from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class ProviderFailureMonitor:
    window_seconds: int
    threshold: int
    alert_cooldown_seconds: int
    _events: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _last_alert_at: dict[str, float] = field(default_factory=dict)

    def record(self, provider: str) -> tuple[bool, int]:
        now = time.time()
        events = self._events[provider]
        events.append(now)
        cutoff = now - self.window_seconds
        while events and events[0] < cutoff:
            events.popleft()

        if len(events) < self.threshold:
            return False, len(events)

        last_alert = self._last_alert_at.get(provider, 0.0)
        if now - last_alert < self.alert_cooldown_seconds:
            return False, len(events)

        self._last_alert_at[provider] = now
        return True, len(events)

    def reset(self, provider: str) -> None:
        self._events.pop(provider, None)
        self._last_alert_at.pop(provider, None)
