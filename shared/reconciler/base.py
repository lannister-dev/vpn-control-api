from __future__ import annotations

import abc
import asyncio
import logging
from typing import Any

from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger


class Reconciler(abc.ABC):
    name: str

    def __init__(
        self,
        *,
        interval_sec: int,
        enabled: bool = True,
        tick_lock: RedisTickLock | None = None,
        lock_ttl_sec: int | None = None,
    ) -> None:
        if not getattr(self, "name", None):
            raise ValueError("Reconciler subclass must define a `name`")
        self._interval_sec = max(1, int(interval_sec))
        self._enabled = bool(enabled)
        self._log = StructuredLogger(logging.getLogger(self.name))
        self._tick_lock = tick_lock or RedisTickLock(
            key=f"reconciler:{self.name}",
            ttl_sec=lock_ttl_sec or max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @abc.abstractmethod
    async def tick(self) -> Any:
        ...

    async def is_enabled(self) -> bool:
        return self._enabled

    async def interval_sec(self) -> int:
        return self._interval_sec

    async def start(self):
        if self._task is not None and not self._task.done():
            return
        if not await self.is_enabled():
            self._log.info(f"{self.name}_disabled")
        self._stop_event.clear()
        watchdog.register(self.name)
        self._task = asyncio.create_task(self._run(), name=f"reconciler:{self.name}")

    async def stop(self):
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        watchdog.unregister(self.name)

    async def run_once(self) -> Any:
        if not await self.is_enabled():
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self.tick()

    async def _run(self):
        while not self._stop_event.is_set():
            try:
                interval = max(1, int(await self.interval_sec()))
            except Exception:
                interval = self._interval_sec
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._log.exception(f"{self.name}_tick_failed")
            watchdog.heartbeat(self.name, max_silence_sec=interval * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
