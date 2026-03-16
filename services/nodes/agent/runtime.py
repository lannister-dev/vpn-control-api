from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException

from services.config import NatsConfig
from services.nodes.agent.repository import (
    NodeTransportEventLogRepository,
    NodeTransportOutboxRepository,
    NodeTransportStateRepository,
)
from services.nodes.agent.schemas import (
    AgentSubjects,
    HeartbeatEvent,
    PlacementApplyAckEvent,
    PlacementApplyResultEvent,
    PlacementCommandEvent,
    PlacementCommandPayload,
    SnapshotChunkEvent,
    SnapshotRequestEvent,
    SyncReportAckEvent,
    SyncReportAckStatus,
    SyncReportEvent,
    TransportReportStatus,
)
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import (
    HeartbeatDetails,
    HeartbeatRuntime,
    HeartbeatStats,
    NodeHeartbeatIn,
    NodeSyncReportIn,
)
from services.nodes.service import VpnNodeService
from services.placements.transport import NodeAgentPlacementTransport
from services.placements.schemas import PlacementAppliedState, PlacementApplyResultIn
from services.placements.service import PlacementApplyService
from shared.database.session import AsyncDatabase, WriteAwareAsyncSession
from shared.nats.nats import NatsClient
from shared.utils.logger import StructuredLogger


logger_transport = StructuredLogger(logging.getLogger("node-agent-transport"))


class NodeAgentRuntime:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nats = NatsClient(config)
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._subjects = AgentSubjects(
            command_prefix=config.js_command_subject_prefix,
            result_prefix=config.js_result_subject_prefix,
            snapshot_prefix=config.js_snapshot_subject_prefix,
            heartbeat_prefix=config.js_heartbeat_subject_prefix,
            sync_report_prefix=config.js_sync_report_subject_prefix,
        )

    async def start(self) -> None:
        if not self._config.enabled:
            logger_transport.info("node_agent_transport_disabled")
            return
        await self._nats.connect()
        await self._ensure_topology()
        self._running = True
        self._tasks = [
            asyncio.create_task(self._run_outbox_publisher(), name="node-agent-outbox-publisher"),
            asyncio.create_task(
                self._run_consumer_loop(
                    subject=f"{self._config.js_result_subject_prefix}.*.results",
                    durable=f"{self._config.js_consumer_prefix}-placement-results",
                    handler=self._handle_result_message,
                ),
                name="node-agent-placement-results-consumer",
            ),
            asyncio.create_task(
                self._run_consumer_loop(
                    subject=f"{self._config.js_snapshot_subject_prefix}.*.request",
                    durable=f"{self._config.js_consumer_prefix}-snapshot-requests",
                    handler=self._handle_snapshot_request_message,
                ),
                name="node-agent-snapshot-request-consumer",
            ),
            asyncio.create_task(
                self._run_consumer_loop(
                    subject=f"{self._config.js_heartbeat_subject_prefix}.*.events",
                    durable=f"{self._config.js_consumer_prefix}-heartbeats",
                    handler=self._handle_heartbeat_message,
                ),
                name="node-agent-heartbeat-consumer",
            ),
            asyncio.create_task(
                self._run_consumer_loop(
                    subject=f"{self._config.js_sync_report_subject_prefix}.*.events",
                    durable=f"{self._config.js_consumer_prefix}-sync-reports",
                    handler=self._handle_sync_report_message,
                ),
                name="node-agent-sync-report-consumer",
            ),
        ]
        logger_transport.info("node_agent_transport_started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        await self._nats.close()
        logger_transport.info("node_agent_transport_stopped")

    async def _ensure_topology(self) -> None:
        await self._nats.ensure_stream(
            name=self._config.js_command_stream,
            subjects=[f"{self._config.js_command_subject_prefix}.*.commands"],
        )
        await self._nats.ensure_stream(
            name=self._config.js_result_stream,
            subjects=[
                f"{self._config.js_result_subject_prefix}.*.results",
                f"{self._config.js_result_subject_prefix}.*.acks",
                f"{self._config.js_snapshot_subject_prefix}.*.request",
                f"{self._config.js_snapshot_subject_prefix}.*.chunks",
            ],
        )
        await self._nats.ensure_stream(
            name=self._config.js_control_stream,
            subjects=[
                f"{self._config.js_heartbeat_subject_prefix}.*.events",
                f"{self._config.js_sync_report_subject_prefix}.*.events",
                f"{self._config.js_sync_report_subject_prefix}.*.acks",
            ],
        )

    async def _run_outbox_publisher(self) -> None:
        while self._running:
            try:
                published = await self._publish_outbox_batch()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger_transport.exception("node_agent_outbox_publish_failed")
                published = 0
            if published <= 0:
                await asyncio.sleep(self._config.js_outbox_poll_interval_s)

    async def _publish_outbox_batch(self) -> int:
        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            outbox_repo = NodeTransportOutboxRepository(session)
            state_repo = NodeTransportStateRepository(session)
            rows = await outbox_repo.claim_batch(
                now=datetime.now(timezone.utc),
                limit=self._config.js_outbox_batch_size,
            )
            if not rows:
                await session.rollback()
                return 0

            published = 0
            for row in rows:
                payload = PlacementCommandPayload.model_validate(row.payload)
                state = await state_repo.get_or_create(node_id=payload.node_id)
                emitted_at = datetime.now(timezone.utc)
                event = PlacementCommandEvent(
                    node_id=str(payload.node_id),
                    emitted_at=emitted_at,
                    snapshot_id=state.last_snapshot_id,
                    epoch=state.current_epoch,
                    event_id=row.message_id,
                    placement_id=str(payload.placement_id),
                    key_id=str(payload.key_id),
                    op_version=payload.op_version,
                    desired_state=payload.desired_state,
                    backend_node_id=str(payload.backend_node_id),
                    protocol=payload.protocol,
                    transport=payload.transport,
                    client_id=payload.client_id,
                    is_revoked=payload.is_revoked,
                    valid_until=payload.valid_until,
                    updated_at=payload.updated_at,
                )
                try:
                    await self._nats.publish_jetstream(
                        subject=row.subject,
                        payload=event.model_dump(mode="json"),
                        msg_id=row.message_id,
                    )
                except Exception as exc:
                    await outbox_repo.mark_failed(
                        outbox_id=row.id,
                        error=str(exc),
                        next_retry_at=emitted_at + timedelta(seconds=5),
                    )
                    logger_transport.warning(
                        "node_agent_command_publish_retry_scheduled",
                        outbox_id=str(row.id),
                        message_id=row.message_id,
                        error=str(exc),
                    )
                    continue

                await outbox_repo.mark_published(outbox_id=row.id, published_at=emitted_at)
                await state_repo.touch_command(
                    node_id=payload.node_id,
                    message_id=row.message_id,
                    at=emitted_at,
                )
                published += 1

            if session.has_pending_writes():
                await session.commit()
            else:
                await session.rollback()
            return published

    async def _run_consumer_loop(self, *, subject: str, durable: str, handler) -> None:
        subscription = await self._nats.pull_subscribe(
            subject=subject,
            durable=durable,
            ack_wait_s=self._config.js_ack_wait_s,
            max_deliver=self._config.js_max_deliver,
        )
        while self._running:
            try:
                messages = await self._nats.fetch_messages(
                    subscription,
                    batch=self._config.js_outbox_batch_size,
                    timeout=self._config.js_fetch_timeout_s,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if "timeout" in str(exc).lower():
                    continue
                logger_transport.exception(
                    "node_agent_consumer_fetch_failed",
                    subject=subject,
                    durable=durable,
                )
                await asyncio.sleep(1.0)
                continue

            for msg in messages:
                try:
                    should_ack = await handler(msg)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger_transport.exception(
                        "node_agent_consumer_message_failed",
                        subject=getattr(msg, "subject", subject),
                    )
                    should_ack = False
                if should_ack:
                    await msg.ack()

    async def _handle_result_message(self, msg) -> bool:
        event = PlacementApplyResultEvent.model_validate_json(msg.data.decode())
        node_id = self._parse_node_id(event.node_id)
        if node_id is None:
            logger_transport.warning("placement_result_invalid_node_id", node_id=event.node_id)
            return True

        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            if not await self._resolve_node(session, node_id):
                logger_transport.warning("placement_result_unknown_node", node_id=str(node_id))
                await session.rollback()
                return True

            event_log_repo = NodeTransportEventLogRepository(session)
            is_new = await event_log_repo.record_if_new(
                node_id=node_id,
                event_type="placement_result",
                event_id=event.event_id,
                subject=getattr(msg, "subject", None),
                payload=event.model_dump(mode="json"),
                processed_at=datetime.now(timezone.utc),
            )
            if not is_new:
                await session.rollback()
                return await self._publish_result_ack(
                    node_id=event.node_id,
                    result_event=event,
                    status=TransportReportStatus.skipped_idempotent,
                )

            service = PlacementApplyService(session)
            node = await VpnNodeRepository(session).get_by_id(node_id)
            if node is None:
                await session.rollback()
                return True

            try:
                ack_status = await service.apply_result(
                    node=node,
                    placement_id=UUID(event.placement_id),
                    payload=PlacementApplyResultIn(
                        op_version=event.op_version,
                        applied_state=PlacementAppliedState(event.applied_state.value),
                    ),
                )
            except HTTPException as exc:
                if exc.status_code in {403, 404}:
                    ack_status = "skipped_stale"
                else:
                    raise
            await NodeTransportStateRepository(session).touch_result(
                node_id=node_id,
                event_id=event.event_id,
                at=event.emitted_at,
            )
            await self._finish_session(session)
            return await self._publish_result_ack(
                node_id=event.node_id,
                result_event=event,
                status=TransportReportStatus(ack_status),
            )

    async def _handle_snapshot_request_message(self, msg) -> bool:
        event = SnapshotRequestEvent.model_validate_json(msg.data.decode())
        node_id = self._parse_node_id(event.node_id)
        if node_id is None:
            logger_transport.warning("snapshot_request_invalid_node_id", node_id=event.node_id)
            return True

        request_event_id = self._snapshot_request_event_id(event)
        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            node = await VpnNodeRepository(session).get_by_id(node_id)
            if node is None:
                await session.rollback()
                logger_transport.warning("snapshot_request_unknown_node", node_id=str(node_id))
                return True

            commands = await NodeAgentPlacementTransport(session).list_command_payloads_for_backend(
                backend_node_id=node_id
            )
            state_repo = NodeTransportStateRepository(session)
            snapshot_id = f"snap-{node_id}-{event.requested_at.isoformat()}"
            epoch, reserved_snapshot_id = await state_repo.reserve_snapshot_epoch(
                node_id=node_id,
                request_event_id=request_event_id,
                snapshot_id=snapshot_id,
                snapshot_reason=event.reason.value,
                requested_at=event.requested_at,
                generated_at=datetime.now(timezone.utc),
            )
            snapshot_items = [
                PlacementCommandEvent(
                    node_id=str(command.node_id),
                    emitted_at=datetime.now(timezone.utc),
                    snapshot_id=reserved_snapshot_id,
                    epoch=epoch,
                    event_id=f"snapshot-command:{command.placement_id}:{command.op_version}",
                    placement_id=str(command.placement_id),
                    key_id=str(command.key_id),
                    op_version=command.op_version,
                    desired_state=command.desired_state,
                    backend_node_id=str(command.backend_node_id),
                    protocol=command.protocol,
                    transport=command.transport,
                    client_id=command.client_id,
                    is_revoked=command.is_revoked,
                    valid_until=command.valid_until,
                    updated_at=command.updated_at,
                )
                for command in commands
            ]
            if not snapshot_items:
                await self._publish_snapshot_chunk(
                    node_id=str(node_id),
                    snapshot_id=reserved_snapshot_id,
                    epoch=epoch,
                    chunk_index=0,
                    is_last_chunk=True,
                    items=[],
                )
            else:
                chunked = self._chunk_items(snapshot_items, chunk_size=200)
                for index, chunk in enumerate(chunked):
                    is_last = index == len(chunked) - 1
                    for item in chunk:
                        item.snapshot_complete = is_last
                    await self._publish_snapshot_chunk(
                        node_id=str(node_id),
                        snapshot_id=reserved_snapshot_id,
                        epoch=epoch,
                        chunk_index=index,
                        is_last_chunk=is_last,
                        items=chunk,
                    )

            event_log_repo = NodeTransportEventLogRepository(session)
            await event_log_repo.record_if_new(
                node_id=node_id,
                event_type="snapshot_request",
                event_id=request_event_id,
                subject=getattr(msg, "subject", None),
                payload=event.model_dump(mode="json"),
                processed_at=datetime.now(timezone.utc),
            )
            await self._finish_session(session)
            return True

    async def _handle_heartbeat_message(self, msg) -> bool:
        event = HeartbeatEvent.model_validate_json(msg.data.decode())
        node_id = self._parse_node_id(event.node_id)
        if node_id is None:
            logger_transport.warning("heartbeat_invalid_node_id", node_id=event.node_id)
            return True

        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            node = await VpnNodeRepository(session).get_by_id(node_id)
            if node is None:
                await session.rollback()
                logger_transport.warning("heartbeat_unknown_node", node_id=str(node_id))
                return True

            event_log_repo = NodeTransportEventLogRepository(session)
            is_new = await event_log_repo.record_if_new(
                node_id=node_id,
                event_type="heartbeat",
                event_id=self._heartbeat_event_id(event),
                subject=getattr(msg, "subject", None),
                payload=event.model_dump(mode="json"),
                processed_at=event.emitted_at,
            )
            if not is_new:
                await session.rollback()
                return True

            service = VpnNodeService(session)
            await service.handle_heartbeat(
                node=node,
                payload=NodeHeartbeatIn(
                    agent_version=event.agent_version,
                    is_healthy=event.is_healthy,
                    details=HeartbeatDetails(
                        runtime=HeartbeatRuntime(ready=event.ready, last_error=event.last_error),
                        stats=HeartbeatStats(
                            poll_count=event.poll_count,
                            applied=event.applied,
                            failed=event.failed,
                        ),
                    ),
                ),
            )
            await NodeTransportStateRepository(session).touch_heartbeat(node_id=node_id, at=event.emitted_at)
            await self._finish_session(session)
            return True

    async def _handle_sync_report_message(self, msg) -> bool:
        event = SyncReportEvent.model_validate_json(msg.data.decode())
        node_id = self._parse_node_id(event.node_id)
        if node_id is None:
            logger_transport.warning("sync_report_invalid_node_id", node_id=event.node_id)
            return True

        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            node = await VpnNodeRepository(session).get_by_id(node_id)
            if node is None:
                await session.rollback()
                logger_transport.warning("sync_report_unknown_node", node_id=str(node_id))
                return True

            event_log_repo = NodeTransportEventLogRepository(session)
            is_new = await event_log_repo.record_if_new(
                node_id=node_id,
                event_type="sync_report",
                event_id=self._sync_report_event_id(event),
                subject=getattr(msg, "subject", None),
                payload=event.model_dump(mode="json"),
                processed_at=event.emitted_at,
            )
            if not is_new:
                await session.rollback()
                return await self._publish_sync_report_ack(
                    node_id=event.node_id,
                    ack_event=SyncReportAckEvent(
                        event_id=event.event_id,
                        node_id=event.node_id,
                        emitted_at=datetime.now(timezone.utc),
                        status=SyncReportAckStatus.accepted,
                    ),
                )

            service = VpnNodeService(session)
            accepted = await service.handle_sync_report(
                node=node,
                payload=NodeSyncReportIn(
                    synced_count=event.synced_count,
                    config_version=event.config_version,
                    inventory_hash=event.inventory_hash,
                    inventory_count=event.inventory_count,
                    full_resync_completed=event.full_resync_completed,
                ),
            )
            await NodeTransportStateRepository(session).touch_sync_report(
                node_id=node_id,
                at=event.emitted_at,
            )
            await self._finish_session(session)
            return await self._publish_sync_report_ack(
                node_id=event.node_id,
                ack_event=SyncReportAckEvent(
                    event_id=event.event_id,
                    node_id=event.node_id,
                    emitted_at=datetime.now(timezone.utc),
                    status=(
                        SyncReportAckStatus.accepted
                        if accepted
                        else SyncReportAckStatus.skipped
                    ),
                ),
            )

    async def _publish_snapshot_chunk(
        self,
        *,
        node_id: str,
        snapshot_id: str,
        epoch: int,
        chunk_index: int,
        is_last_chunk: bool,
        items: list[PlacementCommandEvent],
    ) -> None:
        event = SnapshotChunkEvent(
            node_id=node_id,
            emitted_at=datetime.now(timezone.utc),
            snapshot_id=snapshot_id,
            epoch=epoch,
            chunk_index=chunk_index,
            is_last_chunk=is_last_chunk,
            items=items,
        )
        await self._nats.publish_jetstream(
            subject=self._subjects.snapshot_chunk(node_id),
            payload=event.model_dump(mode="json"),
            msg_id=f"snapshot-chunk:{node_id}:{snapshot_id}:{chunk_index}",
        )

    async def _publish_result_ack(
        self,
        *,
        node_id: str,
        result_event: PlacementApplyResultEvent,
        status: TransportReportStatus,
        error: str | None = None,
    ) -> bool:
        ack_event = PlacementApplyAckEvent(
            node_id=node_id,
            emitted_at=datetime.now(timezone.utc),
            snapshot_id=result_event.snapshot_id,
            epoch=result_event.epoch,
            event_id=result_event.event_id,
            placement_id=result_event.placement_id,
            op_version=result_event.op_version,
            status=status,
            error=error,
        )
        await self._nats.publish_jetstream(
            subject=self._subjects.placement_result_ack(node_id),
            payload=ack_event.model_dump(mode="json"),
            msg_id=f"placement-result-ack:{result_event.event_id}",
        )
        return True

    async def _publish_sync_report_ack(
        self,
        *,
        node_id: str,
        ack_event: SyncReportAckEvent,
    ) -> bool:
        await self._nats.publish_jetstream(
            subject=self._subjects.sync_report_ack(node_id),
            payload=ack_event.model_dump(mode="json"),
            msg_id=f"sync-report-ack:{ack_event.event_id}",
        )
        return True

    @staticmethod
    async def _finish_session(session: WriteAwareAsyncSession) -> None:
        if session.has_pending_writes():
            await session.commit()
        else:
            await session.rollback()

    @staticmethod
    def _parse_node_id(raw: str) -> UUID | None:
        try:
            return UUID(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _heartbeat_event_id(event: HeartbeatEvent) -> str:
        return event.event_id

    @staticmethod
    def _sync_report_event_id(event: SyncReportEvent) -> str:
        return event.event_id

    @staticmethod
    def _snapshot_request_event_id(event: SnapshotRequestEvent) -> str:
        return (
            f"snapshot-request:{event.node_id}:{event.reason.value}:"
            f"{event.requested_at.isoformat()}:{event.known_snapshot_id or ''}"
        )

    @staticmethod
    def _chunk_items(items: list[PlacementCommandEvent], *, chunk_size: int) -> list[list[PlacementCommandEvent]]:
        return [items[idx: idx + chunk_size] for idx in range(0, len(items), chunk_size)]

    @staticmethod
    async def _resolve_node(session: WriteAwareAsyncSession, node_id: UUID) -> bool:
        node = await VpnNodeRepository(session).get_by_id(node_id)
        return node is not None
