from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.finance.constants import MATERIALIZE_TICK_SEC
from services.finance.service import FinanceService
from shared.database.session import AsyncDatabase
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("finance-materialize-templates-reconciler"))


class FinanceMaterializeTemplatesReconciler(Reconciler):
    name = "finance_materialize_templates"

    def __init__(self, *, tick_lock: RedisTickLock | None = None):
        super().__init__(interval_sec=MATERIALIZE_TICK_SEC, tick_lock=tick_lock)
        self._session_maker = AsyncDatabase.get_session_maker()

    async def tick(self) -> int:
        async with self._session_maker() as session:
            service = FinanceService(session)
            now = datetime.now(timezone.utc)
            created = await service.materialize_due_templates(now)
            if created:
                await session.commit()
                logger.info("finance_expenses_materialized", count=created)
            return created
