from __future__ import annotations

import time
from threading import RLock

from shared.reconciler.constants import INITIAL_GRACE_SEC
from shared.reconciler.schemas import ReconcilerStatus


class ReconcilerWatchdog:
    def __init__(self):
        self._lock = RLock()
        self._last_tick: dict[str, float] = {}
        self._max_silence: dict[str, float] = {}

    def register(self, name: str) -> None:
        with self._lock:
            if name not in self._last_tick:
                self._last_tick[name] = time.monotonic()
                self._max_silence[name] = INITIAL_GRACE_SEC

    def unregister(self, name: str) -> None:
        with self._lock:
            self._last_tick.pop(name, None)
            self._max_silence.pop(name, None)

    def heartbeat(self, name: str, *, max_silence_sec: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._last_tick[name] = now
            self._max_silence[name] = max(1.0, float(max_silence_sec))

    def statuses(self) -> list[ReconcilerStatus]:
        now = time.monotonic()
        out: list[ReconcilerStatus] = []
        with self._lock:
            for name, last in self._last_tick.items():
                limit = self._max_silence.get(name, INITIAL_GRACE_SEC)
                silence = now - last
                out.append(
                    ReconcilerStatus(
                        name=name,
                        silence_sec=silence,
                        max_silence_sec=limit,
                        alive=silence <= limit,
                    )
                )
        return out

    def is_alive(self) -> bool:
        return all(s.alive for s in self.statuses())


watchdog = ReconcilerWatchdog()
