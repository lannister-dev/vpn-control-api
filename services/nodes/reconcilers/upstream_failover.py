from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.nodes.repository import VpnNodeRepository
from services.routes.service import RouteService
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("upstream-failover-reconciler"))

TICK_SEC = 30


class UpstreamFailoverReconciler(Reconciler):
    name = "upstream_failover"

    def __init__(
        self,
        *,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        route_service_factory: Callable[[AsyncSession], RouteService] | None = None,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        super().__init__(interval_sec=TICK_SEC, tick_lock=tick_lock)
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._route_service_factory = route_service_factory or RouteService

    async def tick(self) -> int:
        async with self._session_maker() as session:
            repo = VpnNodeRepository(session)
            dead = await repo.list_entries_with_dead_upstream()
            if not dead:
                return 0
            live = await repo.list_live_backends()
            if not live:
                logger.warning("upstream_failover_no_live_backend", entries=[n.name for n in dead])
                return 0

            chosen = live[0]
            route_service = self._route_service_factory(session)
            applied = 0
            for entry in dead:
                await route_service.sync_entry_upstream(
                    entry_node_id=entry.id,
                    backend_node_id=chosen.id,
                    backend_node=chosen,
                )
                applied += 1
                logger.info(
                    "upstream_failover_applied",
                    entry=entry.name,
                    entry_id=str(entry.id),
                    old_upstream_id=str(entry.upstream_node_id) if entry.upstream_node_id else None,
                    new_upstream=chosen.name,
                    new_upstream_id=str(chosen.id),
                )
            await session.commit()
            return applied
