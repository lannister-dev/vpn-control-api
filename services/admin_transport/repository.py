from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing import cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_transport.read_models import (
    EventLogSummaryRow,
    OutboxSummaryRow,
    TransportEventRow,
    TransportEventWithNodeRow,
    TransportNodeRow,
    TransportOutboxRow,
    TransportOutboxWithNodeRow,
)
from services.nodes.agent.model import (
    NodeTransportEventLog,
    NodeTransportOutbox,
    NodeTransportState,
)
from services.nodes.models import VpnNode


class AdminTransportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest_heartbeat_received_at(self) -> datetime | None:
        stmt = select(func.max(NodeTransportState.last_heartbeat_received_at))
        result = await self.session.execute(stmt)
        return result.scalar()

    # ── Outbox summary ────────────────────────────────────────

    async def get_outbox_summary(self, *, since: datetime) -> OutboxSummaryRow:
        stmt = (
            select(
                NodeTransportOutbox.status,
                func.count().label("cnt"),
            )
            .group_by(NodeTransportOutbox.status)
        )
        rows = (await self.session.execute(stmt)).all()
        by_status = {row.status: row.cnt for row in rows}
        stmt = (
            select(func.count())
            .select_from(NodeTransportOutbox)
            .where(
                NodeTransportOutbox.status == "published",
                NodeTransportOutbox.published_at >= since,
            )
        )
        return OutboxSummaryRow(
            pending=by_status.get("pending", 0),
            failed=by_status.get("failed", 0),
            publishing=by_status.get("publishing", 0),
            published_24h=(await self.session.execute(stmt)).scalar_one(),
        )

    # ── Event log summary ─────────────────────────────────────

    _EXCLUDED_EVENT_TYPES = {"heartbeat", "sync_report"}

    async def get_event_log_summary(self, *, since: datetime) -> EventLogSummaryRow:
        stmt = (
            select(
                NodeTransportEventLog.event_type,
                func.count().label("cnt"),
            )
            .where(NodeTransportEventLog.processed_at >= since)
            .where(NodeTransportEventLog.event_type.notin_(self._EXCLUDED_EVENT_TYPES))
            .group_by(NodeTransportEventLog.event_type)
        )
        rows = (await self.session.execute(stmt)).all()
        by_type = {row.event_type: row.cnt for row in rows}
        return EventLogSummaryRow(
            total_24h=sum(by_type.values()),
            by_type=by_type,
        )

    # ── Transport nodes list ──────────────────────────────────

    async def list_transport_nodes(self) -> list[TransportNodeRow]:
        stmt = self._transport_nodes_stmt()
        rows = (await self.session.execute(stmt)).all()
        return [self._build_transport_node_row(row) for row in rows]

    async def get_transport_node(self, node_id: UUID) -> TransportNodeRow | None:
        stmt = self._transport_nodes_stmt(node_id=node_id)
        row = (await self.session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return self._build_transport_node_row(row)

    # ── Node detail ───────────────────────────────────────────

    async def get_recent_events(self, node_id: UUID, *, limit: int = 50) -> list[TransportEventRow]:
        stmt = (
            select(NodeTransportEventLog)
            .where(NodeTransportEventLog.node_id == node_id)
            .where(NodeTransportEventLog.event_type.notin_(self._EXCLUDED_EVENT_TYPES))
            .order_by(NodeTransportEventLog.processed_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            TransportEventRow(
                id=row.id,
                event_type=row.event_type,
                event_id=row.event_id,
                subject=row.subject,
                processed_at=row.processed_at,
                payload=row.payload or {},
            )
            for row in rows
        ]

    async def get_node_outbox_items(self, node_id: UUID) -> list[TransportOutboxRow]:
        stmt = (
            select(NodeTransportOutbox)
            .where(
                NodeTransportOutbox.node_id == node_id,
                NodeTransportOutbox.status != "published",
            )
            .order_by(NodeTransportOutbox.created_at.desc())
            .limit(200)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            TransportOutboxRow(
                id=row.id,
                event_type=row.event_type,
                message_id=row.message_id,
                status=row.status,
                attempts=row.attempts,
                last_error=row.last_error,
                created_at=row.created_at,
                published_at=row.published_at,
                next_retry_at=row.next_retry_at,
            )
            for row in rows
        ]

    # ── Outbox browser ────────────────────────────────────────

    async def list_outbox(
        self,
        *,
        node_id: UUID | None = None,
        status_filter: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TransportOutboxWithNodeRow], int]:
        base = (
            select(
                NodeTransportOutbox,
                VpnNode.name.label("node_name"),
            )
            .outerjoin(VpnNode, VpnNode.id == NodeTransportOutbox.node_id)
        )
        count_base = select(func.count()).select_from(NodeTransportOutbox)

        filters = []
        if node_id is not None:
            filters.append(NodeTransportOutbox.node_id == node_id)
        if status_filter:
            filters.append(NodeTransportOutbox.status == status_filter)
        if event_type:
            filters.append(NodeTransportOutbox.event_type == event_type)

        for f in filters:
            base = base.where(f)
            count_base = count_base.where(f)

        total = (await self.session.execute(count_base)).scalar_one()
        stmt = (
            base
            .order_by(NodeTransportOutbox.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(stmt)).all()
        items = [
            TransportOutboxWithNodeRow(
                id=row.NodeTransportOutbox.id,
                node_id=row.NodeTransportOutbox.node_id,
                node_name=row.node_name,
                event_type=row.NodeTransportOutbox.event_type,
                message_id=row.NodeTransportOutbox.message_id,
                status=row.NodeTransportOutbox.status,
                attempts=row.NodeTransportOutbox.attempts,
                last_error=row.NodeTransportOutbox.last_error,
                created_at=row.NodeTransportOutbox.created_at,
                published_at=row.NodeTransportOutbox.published_at,
                next_retry_at=row.NodeTransportOutbox.next_retry_at,
            )
            for row in rows
        ]
        return items, total

    # ── Outbox retry ──────────────────────────────────────────

    async def retry_outbox_item(self, outbox_id: UUID) -> bool:
        result = await self.session.execute(
            update(NodeTransportOutbox)
            .where(
                NodeTransportOutbox.id == outbox_id,
                NodeTransportOutbox.status == "failed",
            )
            .values(status="pending", next_retry_at=None, last_error=None)
        )
        return (result.rowcount or 0) > 0

    async def retry_all_failed(self, node_id: UUID | None = None) -> int:
        stmt = (
            update(NodeTransportOutbox)
            .where(NodeTransportOutbox.status == "failed")
            .values(status="pending", next_retry_at=None, last_error=None)
        )
        if node_id is not None:
            stmt = stmt.where(NodeTransportOutbox.node_id == node_id)
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def cancel_outbox_item(self, outbox_id: UUID) -> bool:
        result = await self.session.execute(
            delete(NodeTransportOutbox).where(
                NodeTransportOutbox.id == outbox_id,
                NodeTransportOutbox.status.in_(("pending", "failed")),
            )
        )
        return (result.rowcount or 0) > 0

    async def outbox_breakdown_by_type(
        self,
        *,
        node_id: UUID | None,
        status_filter: str | None,
    ) -> list[tuple[str, str, int]]:
        stmt = (
            select(
                NodeTransportOutbox.event_type,
                NodeTransportOutbox.status,
                func.count().label("cnt"),
            )
            .group_by(NodeTransportOutbox.event_type, NodeTransportOutbox.status)
            .order_by(func.count().desc())
        )
        if node_id is not None:
            stmt = stmt.where(NodeTransportOutbox.node_id == node_id)
        if status_filter is not None:
            stmt = stmt.where(NodeTransportOutbox.status == status_filter)
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1], int(row[2])) for row in rows]

    # ── Event log browser ─────────────────────────────────────

    async def list_events(
        self,
        *,
        node_id: UUID | None = None,
        event_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TransportEventWithNodeRow], int]:
        base = (
            select(
                NodeTransportEventLog,
                VpnNode.name.label("node_name"),
            )
            .outerjoin(VpnNode, VpnNode.id == NodeTransportEventLog.node_id)
        )
        count_base = select(func.count()).select_from(NodeTransportEventLog)

        filters = [NodeTransportEventLog.event_type.notin_(self._EXCLUDED_EVENT_TYPES)]
        if node_id is not None:
            filters.append(NodeTransportEventLog.node_id == node_id)
        if event_type:
            filters.append(NodeTransportEventLog.event_type == event_type)
        if date_from is not None:
            filters.append(NodeTransportEventLog.processed_at >= date_from)
        if date_to is not None:
            filters.append(NodeTransportEventLog.processed_at <= date_to)
        if search:
            filters.append(NodeTransportEventLog.event_id.ilike(f"%{search}%"))

        for f in filters:
            base = base.where(f)
            count_base = count_base.where(f)

        total = (await self.session.execute(count_base)).scalar_one()
        stmt = (
            base
            .order_by(NodeTransportEventLog.processed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(stmt)).all()
        items = [
            TransportEventWithNodeRow(
                id=row.NodeTransportEventLog.id,
                node_id=row.NodeTransportEventLog.node_id,
                node_name=row.node_name,
                event_type=row.NodeTransportEventLog.event_type,
                event_id=row.NodeTransportEventLog.event_id,
                subject=row.NodeTransportEventLog.subject,
                processed_at=row.NodeTransportEventLog.processed_at,
                payload=row.NodeTransportEventLog.payload or {},
            )
            for row in rows
        ]
        return items, total

    # ── Helpers ───────────────────────────────────────────────

    # ── Cleanup ─────────────────────────────────────────────────

    async def delete_published_outbox_older_than(self, *, cutoff: datetime) -> int:
        stmt = delete(NodeTransportOutbox).where(
            NodeTransportOutbox.status == "published",
            NodeTransportOutbox.published_at < cutoff,
        )
        result = cast(CursorResult, await self.session.execute(stmt))
        rowcount = result.rowcount
        if callable(rowcount):
            rowcount = rowcount()
        return int(rowcount) if rowcount and rowcount > 0 else 0

    async def delete_events_older_than(self, *, cutoff: datetime) -> int:
        stmt = delete(NodeTransportEventLog).where(
            NodeTransportEventLog.processed_at < cutoff,
        )
        result = cast(CursorResult, await self.session.execute(stmt))
        rowcount = result.rowcount
        if callable(rowcount):
            rowcount = rowcount()
        return int(rowcount) if rowcount and rowcount > 0 else 0

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _build_transport_node_row(row) -> TransportNodeRow:
        return TransportNodeRow(
            node_id=row.node_id,
            name=row.name,
            region=row.region,
            current_epoch=row.current_epoch or 0,
            last_snapshot_id=row.last_snapshot_id,
            last_snapshot_reason=row.last_snapshot_reason,
            last_snapshot_at=row.last_snapshot_requested_at,
            last_snapshot_requested_at=row.last_snapshot_requested_at,
            last_snapshot_generated_at=row.last_snapshot_generated_at,
            last_command_published_at=row.last_command_published_at,
            last_result_received_at=row.last_result_received_at,
            last_heartbeat_received_at=row.last_heartbeat_received_at,
            last_sync_report_received_at=row.last_sync_report_received_at,
            outbox_pending=row.outbox_pending,
            outbox_failed=row.outbox_failed,
        )

    @staticmethod
    def _transport_nodes_stmt(*, node_id: UUID | None = None):
        outbox_sub = (
            select(
                NodeTransportOutbox.node_id,
                func.count()
                .filter(NodeTransportOutbox.status.in_(("pending", "publishing")))
                .label("outbox_pending"),
                func.count()
                .filter(NodeTransportOutbox.status == "failed")
                .label("outbox_failed"),
            )
            .group_by(NodeTransportOutbox.node_id)
            .subquery()
        )

        stmt = (
            select(
                VpnNode.id.label("node_id"),
                VpnNode.name,
                VpnNode.region,
                NodeTransportState.current_epoch,
                NodeTransportState.last_snapshot_id,
                NodeTransportState.last_snapshot_reason,
                NodeTransportState.last_snapshot_requested_at,
                NodeTransportState.last_snapshot_generated_at,
                NodeTransportState.last_command_published_at,
                NodeTransportState.last_result_received_at,
                NodeTransportState.last_heartbeat_received_at,
                NodeTransportState.last_sync_report_received_at,
                func.coalesce(outbox_sub.c.outbox_pending, 0).label("outbox_pending"),
                func.coalesce(outbox_sub.c.outbox_failed, 0).label("outbox_failed"),
            )
            .select_from(VpnNode)
            .outerjoin(NodeTransportState, NodeTransportState.node_id == VpnNode.id)
            .outerjoin(outbox_sub, outbox_sub.c.node_id == VpnNode.id)
            .where(VpnNode.is_active.is_(True))
        )
        if node_id is not None:
            stmt = stmt.where(VpnNode.id == node_id)
        return stmt.order_by(VpnNode.name)
