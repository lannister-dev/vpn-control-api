from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin.transport.presenters import (
    to_event_with_node_out,
    to_outbox_item_with_node_out,
    to_transport_event_out,
    to_transport_node_out,
    to_transport_outbox_item_out,
)
from services.admin.transport.repository import AdminTransportRepository
from services.admin.transport.schemas import (
    ConsumerTaskStatus,
    EventLogListOut,
    EventLogSummary,
    ForceSnapshotOut,
    OutboxBreakdownItem,
    OutboxListOut,
    OutboxRetryAllOut,
    OutboxRetryOut,
    OutboxSummary,
    TransportCleanupOut,
    TransportNodeDetailOut,
    TransportNodeListOut,
    TransportOverviewOut,
)
from services.config import get_settings
from services.nodes.agent.admin_snapshot import AdminSnapshotPublisher
from services.nodes.agent.repository import NodeTransportStateRepository
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient


class AdminTransportService:
    def __init__(self, session: AsyncSession, request: Request | None = None):
        self.session = session
        self.repo = AdminTransportRepository(session)
        self._request = request
        settings = get_settings()
        self._nats_config = settings.nats

    def _get_runtime(self):
        if self._request is None:
            return None
        return getattr(self._request.app.state, "node_agent_runtime", None)

    def _get_admin_nats_client(self) -> NatsClient | None:
        if self._request is None:
            return None
        return getattr(self._request.app.state, "nats_client", None)

    async def _derive_nats_from_activity(self, now: datetime) -> bool:
        latest_hb = await self.repo.get_latest_heartbeat_received_at()
        if latest_hb is None:
            return False
        if latest_hb.tzinfo is None:
            latest_hb = latest_hb.replace(tzinfo=timezone.utc)
        return (now - latest_hb).total_seconds() < 90

    async def get_overview(self) -> TransportOverviewOut:
        now = datetime.now(timezone.utc)
        since_24h = now - timedelta(hours=24)

        runtime = self._get_runtime()
        admin_nats = self._get_admin_nats_client()
        nats_connected = False
        uptime_s = None
        consumer_tasks: list[ConsumerTaskStatus] = []
        if runtime is not None:
            status = runtime.get_runtime_status()
            uptime_s = status.uptime_s
            consumer_tasks = [
                ConsumerTaskStatus(name=t.name, running=t.running, error=t.error)
                for t in status.tasks
            ]
            if runtime.is_leader:
                nats_connected = status.nats_connected
            else:
                nats_connected = await self._derive_nats_from_activity(now)
        elif admin_nats is not None:
            nats_connected = admin_nats.is_connected
            if not nats_connected:
                nats_connected = await self._derive_nats_from_activity(now)
        else:
            nats_connected = await self._derive_nats_from_activity(now)

        outbox_summary = await self.repo.get_outbox_summary(since=since_24h)
        event_summary = await self.repo.get_event_log_summary(since=since_24h)

        return TransportOverviewOut(
            generated_at=now,
            nats_connected=nats_connected,
            uptime_s=uptime_s,
            consumer_tasks=consumer_tasks,
            outbox=OutboxSummary(**outbox_summary.model_dump()),
            events=EventLogSummary(**event_summary.model_dump()),
        )

    async def list_transport_nodes(self) -> TransportNodeListOut:
        now = datetime.now(timezone.utc)
        nodes = await self.repo.list_transport_nodes()
        return TransportNodeListOut(
            items=[to_transport_node_out(node, now=now) for node in nodes],
        )

    async def get_transport_node_detail(self, node_id: UUID) -> TransportNodeDetailOut:
        now = datetime.now(timezone.utc)
        node = await self.repo.get_transport_node(node_id)
        if node is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Node not found")

        events = await self.repo.get_recent_events(node_id, limit=50)
        outbox_items = await self.repo.get_node_outbox_items(node_id)
        node_out = to_transport_node_out(node, now=now)

        return TransportNodeDetailOut(
            **node_out.model_dump(),
            last_snapshot_requested_at=node.last_snapshot_requested_at,
            last_snapshot_generated_at=node.last_snapshot_generated_at,
            recent_events=[to_transport_event_out(event) for event in events],
            outbox_items=[to_transport_outbox_item_out(item) for item in outbox_items],
        )

    async def list_outbox(
        self,
        *,
        node_id: UUID | None = None,
        status_filter: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OutboxListOut:
        items, total = await self.repo.list_outbox(
            node_id=node_id,
            status_filter=status_filter,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )
        return OutboxListOut(
            items=[to_outbox_item_with_node_out(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def retry_outbox_item(self, outbox_id: UUID) -> OutboxRetryOut:
        ok = await self.repo.retry_outbox_item(outbox_id)
        if ok:
            await self.session.commit()
        return OutboxRetryOut(ok=ok)

    async def retry_all_failed(self, node_id: UUID | None = None) -> OutboxRetryAllOut:
        count = await self.repo.retry_all_failed(node_id)
        if count > 0:
            await self.session.commit()
        return OutboxRetryAllOut(retried_count=count)

    async def cancel_outbox_item(self, outbox_id: UUID) -> OutboxRetryOut:
        ok = await self.repo.cancel_outbox_item(outbox_id)
        if ok:
            await self.session.commit()
        return OutboxRetryOut(ok=ok)

    async def outbox_breakdown_by_type(
        self,
        *,
        node_id: UUID | None = None,
        status_filter: str | None = None,
    ) -> list[OutboxBreakdownItem]:
        rows = await self.repo.outbox_breakdown_by_type(node_id=node_id, status_filter=status_filter)
        return [OutboxBreakdownItem(event_type=et, status=st, count=c) for et, st, c in rows]

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
    ) -> EventLogListOut:
        items, total = await self.repo.list_events(
            node_id=node_id,
            event_type=event_type,
            date_from=date_from,
            date_to=date_to,
            search=search,
            limit=limit,
            offset=offset,
        )
        return EventLogListOut(
            items=[to_event_with_node_out(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def cleanup_old_data(self) -> TransportCleanupOut:
        from services.admin.transport.policy.repository import TransportPolicyRepository
        policy = (await TransportPolicyRepository(self.session).list(limit=1))[0]
        retention = max(1, int(policy.retention_days))
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        deleted_outbox = await self.repo.delete_published_outbox_older_than(cutoff=cutoff)
        deleted_events = await self.repo.delete_events_older_than(cutoff=cutoff)
        if deleted_outbox > 0 or deleted_events > 0:
            await self.session.commit()
        return TransportCleanupOut(
            deleted_outbox=deleted_outbox,
            deleted_events=deleted_events,
            retention_days=retention,
        )

    async def force_snapshot(self, node_id: UUID) -> ForceSnapshotOut:
        from fastapi import HTTPException

        runtime = self._get_runtime()
        admin_nats = self._get_admin_nats_client()

        if runtime is not None and runtime.is_leader and runtime._nats.is_connected:
            try:
                await runtime.trigger_snapshot_for_node(node_id=node_id, reason="admin_requested")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Snapshot publish failed: {exc}") from exc
        elif admin_nats is not None and admin_nats.is_connected:
            publisher = AdminSnapshotPublisher(nats_client=admin_nats, config=self._nats_config)
            try:
                await publisher.execute(node_id=node_id, reason="admin_requested")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Snapshot publish failed: {exc}") from exc
        else:
            raise HTTPException(
                status_code=503,
                detail="NATS is not available on this process. Ensure NATS is enabled and reachable.",
            )

        state_repo = NodeTransportStateRepository(self.session)
        state = await state_repo.get_or_create(node_id=node_id)
        return ForceSnapshotOut(
            ok=True,
            epoch=state.current_epoch or 0,
            snapshot_id=state.last_snapshot_id or "",
        )


def get_admin_transport_service(
    request: Request,
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> AdminTransportService:
    return AdminTransportService(session, request=request)
