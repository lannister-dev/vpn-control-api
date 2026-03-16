from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.agent.model import (
    NodeTransportEventLog,
    NodeTransportOutbox,
    NodeTransportState,
)
from shared.database.base_repository import BaseRepository


class NodeTransportOutboxRepository(BaseRepository[NodeTransportOutbox]):
    def __init__(self, session: AsyncSession):
        super().__init__(NodeTransportOutbox, session)

    async def enqueue_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        stmt = insert(NodeTransportOutbox).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=[NodeTransportOutbox.message_id])
        await self.session.execute(stmt)

    async def claim_batch(self, *, now: datetime, limit: int) -> list[NodeTransportOutbox]:
        stmt = (
            select(NodeTransportOutbox)
            .where(NodeTransportOutbox.status.in_(("pending", "failed")))
            .where(
                (NodeTransportOutbox.next_retry_at.is_(None))
                | (NodeTransportOutbox.next_retry_at <= now)
            )
            .order_by(NodeTransportOutbox.created_at.asc(), NodeTransportOutbox.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        if not rows:
            return []
        await self.session.execute(
            update(NodeTransportOutbox)
            .where(NodeTransportOutbox.id.in_([row.id for row in rows]))
            .values(
                status="publishing",
                attempts=NodeTransportOutbox.attempts + 1,
                updated_at=func.now(),
            )
        )
        return rows

    async def mark_published(self, *, outbox_id: UUID, published_at: datetime) -> None:
        await self.session.execute(
            update(NodeTransportOutbox)
            .where(NodeTransportOutbox.id == outbox_id)
            .values(
                status="published",
                published_at=published_at,
                next_retry_at=None,
                last_error=None,
                updated_at=func.now(),
            )
        )

    async def mark_failed(self, *, outbox_id: UUID, error: str, next_retry_at: datetime) -> None:
        await self.session.execute(
            update(NodeTransportOutbox)
            .where(NodeTransportOutbox.id == outbox_id)
            .values(
                status="failed",
                last_error=error[:4000],
                next_retry_at=next_retry_at,
                updated_at=func.now(),
            )
        )


class NodeTransportEventLogRepository(BaseRepository[NodeTransportEventLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(NodeTransportEventLog, session)

    async def record_if_new(
        self,
        *,
        node_id: UUID,
        event_type: str,
        event_id: str,
        subject: str | None,
        payload: dict,
        processed_at: datetime,
    ) -> bool:
        stmt = insert(NodeTransportEventLog).values(
            node_id=node_id,
            event_type=event_type,
            event_id=event_id,
            subject=subject,
            payload=payload,
            processed_at=processed_at,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=[NodeTransportEventLog.event_id])
        result = await self.session.execute(stmt)
        rowcount = getattr(result, "rowcount", None)
        if callable(rowcount):
            rowcount = rowcount()
        return bool(rowcount and rowcount > 0)


class NodeTransportStateRepository(BaseRepository[NodeTransportState]):
    def __init__(self, session: AsyncSession):
        super().__init__(NodeTransportState, session)

    async def get_or_create(self, *, node_id: UUID) -> NodeTransportState:
        existing = await self.get_one_by(node_id=node_id)
        if existing is not None:
            return existing
        stmt = insert(NodeTransportState).values(node_id=node_id, current_epoch=0)
        stmt = stmt.on_conflict_do_nothing(index_elements=[NodeTransportState.node_id])
        await self.session.execute(stmt)
        created = await self.get_one_by(node_id=node_id)
        if created is None:
            raise RuntimeError("failed to create node transport state")
        return created

    async def reserve_snapshot_epoch(
        self,
        *,
        node_id: UUID,
        request_event_id: str,
        snapshot_id: str,
        snapshot_reason: str,
        requested_at: datetime,
        generated_at: datetime,
    ) -> tuple[int, str]:
        await self.get_or_create(node_id=node_id)
        result = await self.session.execute(
            select(NodeTransportState)
            .where(NodeTransportState.node_id == node_id)
            .with_for_update()
        )
        state = result.scalar_one()
        if state.last_snapshot_request_event_id == request_event_id and state.last_snapshot_id:
            return int(state.current_epoch or 0), state.last_snapshot_id
        new_epoch = int(state.current_epoch or 0) + 1
        await self.session.execute(
            update(NodeTransportState)
            .where(NodeTransportState.node_id == node_id)
            .values(
                current_epoch=new_epoch,
                last_snapshot_id=snapshot_id,
                last_snapshot_request_event_id=request_event_id,
                last_snapshot_requested_at=requested_at,
                last_snapshot_generated_at=generated_at,
                last_snapshot_reason=snapshot_reason,
                updated_at=func.now(),
            )
        )
        return new_epoch, snapshot_id

    async def touch_command(self, *, node_id: UUID, message_id: str, at: datetime) -> None:
        await self.get_or_create(node_id=node_id)
        await self.session.execute(
            update(NodeTransportState)
            .where(NodeTransportState.node_id == node_id)
            .values(
                last_command_published_at=at,
                last_command_message_id=message_id,
                updated_at=func.now(),
            )
        )

    async def touch_result(self, *, node_id: UUID, event_id: str, at: datetime) -> None:
        await self.get_or_create(node_id=node_id)
        await self.session.execute(
            update(NodeTransportState)
            .where(NodeTransportState.node_id == node_id)
            .values(
                last_result_received_at=at,
                last_result_event_id=event_id,
                updated_at=func.now(),
            )
        )

    async def touch_heartbeat(self, *, node_id: UUID, at: datetime) -> None:
        await self.get_or_create(node_id=node_id)
        await self.session.execute(
            update(NodeTransportState)
            .where(NodeTransportState.node_id == node_id)
            .values(last_heartbeat_received_at=at, updated_at=func.now())
        )

    async def touch_sync_report(self, *, node_id: UUID, at: datetime) -> None:
        await self.get_or_create(node_id=node_id)
        await self.session.execute(
            update(NodeTransportState)
            .where(NodeTransportState.node_id == node_id)
            .values(last_sync_report_received_at=at, updated_at=func.now())
        )
