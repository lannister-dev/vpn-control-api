from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.alerts.models import AlertEvent


class AlertEventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_active_by_dedup(
        self,
        *,
        source: str,
        dedup_key: str,
        within_seconds: int,
    ) -> AlertEvent | None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
        stmt = (
            select(AlertEvent)
            .where(AlertEvent.source == source)
            .where(AlertEvent.dedup_key == dedup_key)
            .where(AlertEvent.resolved_at.is_(None))
            .where(AlertEvent.dismissed_at.is_(None))
            .where(AlertEvent.last_seen_at >= cutoff)
            .order_by(AlertEvent.last_seen_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def insert(
        self,
        *,
        level: str,
        source: str,
        title: str,
        body: str,
        dedup_key: str | None,
        entity_id: str | None,
        telegram_sent: bool,
    ) -> AlertEvent:
        now = datetime.now(timezone.utc)
        row = AlertEvent(
            level=level,
            source=source,
            title=title,
            body=body,
            dedup_key=dedup_key,
            entity_id=entity_id,
            last_seen_at=now,
            telegram_sent_at=now if telegram_sent else None,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def bump_existing(self, alert: AlertEvent, *, telegram_sent: bool) -> AlertEvent:
        alert.occurrences = (alert.occurrences or 0) + 1
        alert.last_seen_at = datetime.now(timezone.utc)
        if telegram_sent:
            alert.telegram_sent_at = alert.last_seen_at
        await self.session.flush()
        return alert

    async def resolve_active(self, *, source: str, dedup_key: str) -> int:
        now = datetime.now(timezone.utc)
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.source == source)
            .where(AlertEvent.dedup_key == dedup_key)
            .where(AlertEvent.resolved_at.is_(None))
            .where(AlertEvent.dismissed_at.is_(None))
            .values(resolved_at=now, updated_at=now)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def list_paginated(
        self,
        *,
        unread_only: bool = False,
        active_only: bool = True,
        level: str | None = None,
        source: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AlertEvent], int]:
        base = select(AlertEvent)
        if unread_only:
            base = base.where(AlertEvent.read_at.is_(None))
        if active_only:
            base = base.where(AlertEvent.dismissed_at.is_(None))
        if level:
            base = base.where(AlertEvent.level == level)
        if source:
            base = base.where(AlertEvent.source == source)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            base.order_by(AlertEvent.last_seen_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return rows, total

    async def count_unread(self) -> int:
        stmt = (
            select(func.count())
            .select_from(AlertEvent)
            .where(AlertEvent.read_at.is_(None))
            .where(AlertEvent.dismissed_at.is_(None))
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_by_id(self, alert_id: UUID) -> AlertEvent | None:
        stmt = select(AlertEvent).where(AlertEvent.id == alert_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def mark_read(self, alert_id: UUID) -> bool:
        now = datetime.now(timezone.utc)
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.id == alert_id)
            .where(AlertEvent.read_at.is_(None))
            .values(read_at=now, updated_at=now)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0) > 0

    async def mark_all_read(self) -> int:
        now = datetime.now(timezone.utc)
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.read_at.is_(None))
            .where(AlertEvent.dismissed_at.is_(None))
            .values(read_at=now, updated_at=now)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def dismiss(self, alert_id: UUID) -> bool:
        now = datetime.now(timezone.utc)
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.id == alert_id)
            .where(AlertEvent.dismissed_at.is_(None))
            .values(dismissed_at=now, updated_at=now)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0) > 0
