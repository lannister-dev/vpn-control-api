from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.config import get_settings
from services.scenarios.constants import (
    SCENARIO_DUE_BATCH_SIZE,
    SCENARIO_RECONCILER_INTERVAL_SEC,
)
from services.scenarios.service import ScenarioService
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("scenario-reconciler"))


class ScenarioReconciler(Reconciler):
    name = "scenario"

    def __init__(
        self,
        *,
        nats_client: NatsClient | None = None,
        interval_sec: int = SCENARIO_RECONCILER_INTERVAL_SEC,
        batch_size: int = SCENARIO_DUE_BATCH_SIZE,
        tick_lock: RedisTickLock | None = None,
    ):
        super().__init__(interval_sec=max(30, int(interval_sec)), tick_lock=tick_lock)
        self._nats = nats_client
        self._batch_size = max(1, int(batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
        async with self._session_maker() as session:
            svc = ScenarioService(
                session,
                nats_client=self._nats,
                outbound_subject=get_settings().nats.support_outbound_subject,
            )
            now = datetime.now(timezone.utc)
            sent = await svc.run_due(now=now, limit=self._batch_size)
            await session.commit()
            if sent:
                logger.info("scenario_messages_sent", count=sent)
            return sent
