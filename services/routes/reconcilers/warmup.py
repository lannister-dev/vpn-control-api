from __future__ import annotations

import logging

from services.config import get_settings
from services.routes.service import RouteService
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger


class RouteWarmupReconciler(Reconciler):
    name = "route_warmup"

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        interval_sec = max(30, get_settings().routes.warmup_tick_sec)
        super().__init__(
            interval_sec=interval_sec,
            tick_lock=tick_lock,
            lock_ttl_sec=max(30, interval_sec * 2),
        )
        self._session_maker = AsyncDatabase.get_session_maker()
        self._log = StructuredLogger(logging.getLogger("route-warmup-reconciler"))

    async def tick(self):
        async with self._session_maker() as session:
            tick = await RouteService(session).advance_warmup()
            await session.commit()
            if tick.processed > 0:
                self._log.info(
                    "route_warmup_tick",
                    processed=tick.processed,
                    advanced=tick.advanced,
                    finalized=tick.finalized,
                )
            return tick
