from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.nats_dedup.models import NatsProcessedMsgLog


class NatsMessageDedupRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def claim(self, *, subject: str, msg_id: str) -> bool:
        if not msg_id:
            return True
        try:
            self.session.add(NatsProcessedMsgLog(subject=subject, msg_id=msg_id))
            await self.session.flush()
            return True
        except IntegrityError:
            await self.session.rollback()
            return False

    async def cleanup_older_than(self, *, retention: timedelta) -> int:
        cutoff = datetime.now(timezone.utc) - retention
        result = await self.session.execute(
            delete(NatsProcessedMsgLog).where(NatsProcessedMsgLog.created_at < cutoff)
        )
        return int(result.rowcount or 0)
