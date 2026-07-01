from __future__ import annotations

import logging
import re

from services.config import get_settings
from services.nodes.repository import VpnNodeRepository
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("nats-consumer-cleanup-reconciler"))

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


class NatsConsumerCleanupReconciler(Reconciler):
    name = "nats_consumer_cleanup"

    def __init__(
        self,
        *,
        nats_client: NatsClient | None = None,
        interval_sec: int = 3600,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(interval_sec=max(300, int(interval_sec)), tick_lock=tick_lock, lock_ttl_sec=600)
        self._nats_client = nats_client
        self._session_maker = AsyncDatabase.get_session_maker()

    async def is_enabled(self) -> bool:
        return self._nats_client is not None

    async def tick(self) -> int:
        if self._nats_client is None:
            return 0
        settings = get_settings()
        streams = [
            settings.nats.js_command_stream,
            settings.nats.js_result_stream,
            settings.nats.js_control_stream,
        ]
        async with self._session_maker() as session:
            rows = await VpnNodeRepository(session).list_active_with_agent_state()
            await session.commit()
        active = {str(node.id) for node, _ in rows}
        if not active:
            return 0

        removed = 0
        for stream in streams:
            for cname in await self._nats_client.list_consumer_names(stream):
                m = _UUID_RE.search(cname)
                if m is None or m.group(0) in active:
                    continue
                if await self._nats_client.delete_consumer(stream, cname):
                    removed += 1
        if removed:
            logger.info("nats_consumer_cleanup_removed", removed=removed, active_nodes=len(active))
        return removed
