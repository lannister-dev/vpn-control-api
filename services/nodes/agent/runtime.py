from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text

from services.config import NatsConfig
from services.nodes.agent.constants import (
    NODE_AGENT_RUNTIME_LEADER_LOCK_KEY,
    NODE_AGENT_RUNTIME_LEADER_POLL_INTERVAL_S,
    NODE_AGENT_SNAPSHOT_CHUNK_SIZE,
)
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
    PlacementResultApply,
    RuntimeStatus,
    RuntimeTaskStatus,
    SnapshotChunkEvent,
    SnapshotRequestEvent,
    SyncReportAckEvent,
    SyncReportAckStatus,
    SyncReportEvent,
    TransportEventLogInsert,
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
from services.placements.schemas import PlacementAppliedState
from shared.database.session import AsyncDatabase, WriteAwareAsyncSession
from shared.nats.client import NatsClient
from shared.utils.logger import StructuredLogger


logger_transport = StructuredLogger(logging.getLogger("node-agent-transport"))


class NodeAgentRuntime:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nats = NatsClient(config)
        self._running = False
        self._active = False
        self._started_at: datetime | None = None
        self._tasks: list[asyncio.Task] = []
        self._leader_task: asyncio.Task | None = None
        self._leader_connection = None
        self._standby_logged = False
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
        if self._running:
            return
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        self._leader_task = asyncio.create_task(
            self._run_leader_loop(),
            name="node-agent-leader-election",
        )
        logger_transport.info("node_agent_transport_supervisor_started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._leader_task is not None:
            self._leader_task.cancel()
            try:
                await self._leader_task
            except asyncio.CancelledError:
                pass
            self._leader_task = None
        await self._deactivate_runtime()
        await self._release_leader_lock()
        logger_transport.info("node_agent_transport_stopped")

    async def _run_leader_loop(self) -> None:
        while self._running:
            try:
                if not self._has_leader_lock():
                    acquired = await self._try_acquire_leader_lock()
                    if not acquired:
                        if not self._standby_logged:
                            logger_transport.info("node_agent_transport_standby")
                            self._standby_logged = True
                        await asyncio.sleep(NODE_AGENT_RUNTIME_LEADER_POLL_INTERVAL_S)
                        continue
                    self._standby_logged = False
                    await self._activate_runtime()
                if self._leader_connection is not None:
                    await self._leader_connection.execute(text("SELECT 1"))
                await asyncio.sleep(NODE_AGENT_RUNTIME_LEADER_POLL_INTERVAL_S)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger_transport.exception("node_agent_transport_leader_loop_failed")
                await self._deactivate_runtime()
                await self._release_leader_lock()
                await asyncio.sleep(NODE_AGENT_RUNTIME_LEADER_POLL_INTERVAL_S)

    async def _activate_runtime(self) -> None:
        if self._active:
            return
        await self._nats.connect()
        await self._ensure_topology()
        self._tasks = [
            asyncio.create_task(self._run_outbox_publisher(), name="node-agent-outbox-publisher"),
            asyncio.create_task(
                self._run_consumer_loop(
                    subject=f"{self._config.js_result_subject_prefix}.*.results",
                    durable=f"{self._config.js_consumer_prefix}-placement-results",
                    batch_handler=self._handle_result_batch,
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
        self._active = True
        logger_transport.info("node_agent_transport_started")

    async def _deactivate_runtime(self) -> None:
        if not self._active and not self._tasks:
            return
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        await self._nats.close()
        self._active = False
        logger_transport.info("node_agent_transport_deactivated")

    async def _try_acquire_leader_lock(self) -> bool:
        connection = await AsyncDatabase.engine.connect()
        try:
            result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": NODE_AGENT_RUNTIME_LEADER_LOCK_KEY},
            )
            acquired = bool(result.scalar())
            if not acquired:
                await connection.close()
                return False
            self._leader_connection = connection
            logger_transport.info("node_agent_transport_leader_acquired")
            return True
        except Exception:
            await connection.close()
            raise

    async def _release_leader_lock(self) -> None:
        if self._leader_connection is None:
            return
        try:
            await self._leader_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": NODE_AGENT_RUNTIME_LEADER_LOCK_KEY},
            )
        except Exception:
            logger_transport.exception("node_agent_transport_leader_release_failed")
        finally:
            await self._leader_connection.close()
            self._leader_connection = None

    def _has_leader_lock(self) -> bool:
        return self._leader_connection is not None

    @property
    def is_leader(self) -> bool:
        return self._leader_connection is not None

    def get_runtime_status(self) -> RuntimeStatus:
        now = datetime.now(timezone.utc)
        uptime_s = (now - self._started_at).total_seconds() if self._started_at is not None else None
        tasks = [self._task_status(t) for t in self._tasks]
        if self._leader_task is not None:
            tasks.append(self._task_status(self._leader_task))
        return RuntimeStatus(
            nats_connected=self._nats.is_connected,
            uptime_s=uptime_s,
            tasks=tasks,
        )

    @staticmethod
    def _task_status(task: asyncio.Task) -> RuntimeTaskStatus:
        error: str | None = None
        if task.done() and task.exception() is not None:
            try:
                error = str(task.exception())
            except Exception:
                error = "unknown error"
        return RuntimeTaskStatus(
            name=task.get_name(),
            running=not task.done(),
            error=error,
        )

    async def trigger_snapshot_for_node(self, *, node_id: UUID, reason: str = "admin_requested") -> None:
        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            commands = await NodeAgentPlacementTransport(session).list_command_payloads_for_backend(
                backend_node_id=node_id,
            )
            state_repo = NodeTransportStateRepository(session)
            now = datetime.now(timezone.utc)
            snapshot_id = f"snap-{node_id}-admin-{now.isoformat()}"
            request_event_id = f"admin-snapshot:{node_id}:{now.isoformat()}"
            epoch, reserved_snapshot_id = await state_repo.reserve_snapshot_epoch(
                node_id=node_id,
                request_event_id=request_event_id,
                snapshot_id=snapshot_id,
                snapshot_reason=reason,
                requested_at=now,
                generated_at=now,
            )
            snapshot_items = [
                PlacementCommandEvent(
                    node_id=str(cmd.node_id),
                    emitted_at=now,
                    snapshot_id=reserved_snapshot_id,
                    epoch=epoch,
                    event_id=f"snapshot-command:{cmd.placement_id}:{cmd.op_version}",
                    placement_id=str(cmd.placement_id),
                    key_id=str(cmd.key_id),
                    op_version=cmd.op_version,
                    desired_state=cmd.desired_state,
                    backend_node_id=str(cmd.backend_node_id),
                    protocol=cmd.protocol,
                    transport=cmd.transport,
                    client_id=cmd.client_id,
                    is_revoked=cmd.is_revoked,
                    valid_until=cmd.valid_until,
                    updated_at=cmd.updated_at,
                )
                for cmd in commands
            ]
            if not snapshot_items:
                await self._publish_snapshot_chunk(
                    node_id=str(node_id), snapshot_id=reserved_snapshot_id,
                    epoch=epoch, chunk_index=0, is_last_chunk=True, items=[],
                )
            else:
                chunked = self._chunk_items(snapshot_items, chunk_size=NODE_AGENT_SNAPSHOT_CHUNK_SIZE)
                for index, chunk in enumerate(chunked):
                    is_last = index == len(chunked) - 1
                    for item in chunk:
                        item.snapshot_complete = is_last
                    await self._publish_snapshot_chunk(
                        node_id=str(node_id), snapshot_id=reserved_snapshot_id,
                        epoch=epoch, chunk_index=index, is_last_chunk=is_last, items=chunk,
                    )
            await session.commit()

    async def _ensure_topology(self) -> None:
        await self._nats.ensure_stream(
            name=self._config.js_command_stream,
            subjects=[
                f"{self._config.js_command_subject_prefix}.*.commands",
                f"{self._config.js_command_subject_prefix}.*.upstream",
                f"{self._config.js_command_subject_prefix}.*.pool",
            ],
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
                emitted_at = datetime.now(timezone.utc)
                command_payload: PlacementCommandPayload | None = None

                if row.event_type in ("upstream_changed", "pool_changed"):
                    publish_payload = row.payload
                else:
                    command_payload = PlacementCommandPayload.model_validate(row.payload)
                    state = await state_repo.get_or_create(node_id=command_payload.node_id)
                    event = PlacementCommandEvent(
                        node_id=str(command_payload.node_id),
                        emitted_at=emitted_at,
                        snapshot_id=state.last_snapshot_id,
                        epoch=state.current_epoch,
                        event_id=row.message_id,
                        placement_id=str(command_payload.placement_id),
                        key_id=str(command_payload.key_id),
                        op_version=command_payload.op_version,
                        desired_state=command_payload.desired_state,
                        backend_node_id=str(command_payload.backend_node_id),
                        protocol=command_payload.protocol,
                        transport=command_payload.transport,
                        client_id=command_payload.client_id,
                        is_revoked=command_payload.is_revoked,
                        valid_until=command_payload.valid_until,
                        updated_at=command_payload.updated_at,
                    )
                    publish_payload = event.model_dump(mode="json")

                try:
                    await self._nats.publish_jetstream(
                        subject=row.subject,
                        payload=publish_payload,
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
                if command_payload is not None:
                    await state_repo.touch_command(
                        node_id=command_payload.node_id,
                        message_id=row.message_id,
                        at=emitted_at,
                    )
                published += 1

            if session.has_pending_writes():
                await session.commit()
            else:
                await session.rollback()
            return published

    async def _run_consumer_loop(
        self,
        *,
        subject: str,
        durable: str,
        handler=None,
        batch_handler=None,
        concurrency: int = 10,
    ) -> None:
        subscription = await self._nats.pull_subscribe(
            subject=subject,
            durable=durable,
            ack_wait_s=self._config.js_ack_wait_s,
            max_deliver=self._config.js_max_deliver,
        )
        sem = asyncio.Semaphore(concurrency)

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

            if batch_handler:
                try:
                    ack_flags = await batch_handler(messages)
                    for msg, should_ack in zip(messages, ack_flags):
                        if should_ack:
                            await msg.ack()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger_transport.exception(
                        "node_agent_consumer_batch_failed",
                        subject=subject,
                    )
            else:
                async def _handle(msg):
                    async with sem:
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

                await asyncio.gather(*[_handle(msg) for msg in messages])

    async def _handle_result_batch(self, messages: list) -> list[bool]:
        if not messages:
            return []

        parsed: list[tuple] = []
        ack_flags: list[bool] = [False] * len(messages)
        ack_statuses: list[TransportReportStatus | None] = [None] * len(messages)

        for i, msg in enumerate(messages):
            try:
                event = PlacementApplyResultEvent.model_validate_json(msg.data.decode())
            except Exception:
                logger_transport.exception("placement_result_parse_failed")
                ack_flags[i] = True
                continue
            node_id = self._parse_node_id(event.node_id)
            if node_id is None:
                logger_transport.warning("placement_result_invalid_node_id", node_id=event.node_id)
                ack_flags[i] = True
                continue
            parsed.append((i, msg, event, node_id))

        if not parsed:
            return ack_flags

        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            unique_node_ids = {nid for _, _, _, nid in parsed}
            node_repo = VpnNodeRepository(session)
            nodes: dict[UUID, object] = {}
            for nid in unique_node_ids:
                node = await node_repo.get_by_id(nid)
                if node:
                    nodes[nid] = node

            valid: list[tuple] = []
            for i, msg, event, node_id in parsed:
                if node_id not in nodes:
                    logger_transport.warning("placement_result_unknown_node", node_id=str(node_id))
                    ack_flags[i] = True
                    continue
                valid.append((i, msg, event, node_id))

            if not valid:
                await session.rollback()
                return ack_flags

            now = datetime.now(timezone.utc)
            event_log_items = [
                TransportEventLogInsert(
                    node_id=node_id,
                    event_type="placement_result",
                    event_id=event.event_id,
                    subject=getattr(msg, "subject", None),
                    payload=event.model_dump(mode="json"),
                    processed_at=now,
                )
                for _, msg, event, node_id in valid
            ]
            event_log_repo = NodeTransportEventLogRepository(session)
            new_event_ids = await event_log_repo.bulk_record_if_new(
                [item.model_dump(mode="python") for item in event_log_items]
            )

            new_items: list[tuple] = []
            for i, msg, event, node_id in valid:
                if event.event_id not in new_event_ids:
                    ack_flags[i] = True
                    ack_statuses[i] = TransportReportStatus.skipped_idempotent
                else:
                    new_items.append((i, msg, event, node_id))

            if new_items:
                from services.placements.repository import UserPlacementRepository
                placement_repo = UserPlacementRepository(session)
                bulk_items = [
                    PlacementResultApply(
                        id=UUID(event.placement_id),
                        op_version=event.op_version,
                        backend_node_id=nodes[node_id].id,
                        applied_state=event.applied_state.value,
                        applied_version=event.op_version,
                        updated_at=now,
                    )
                    for _, _, event, node_id in new_items
                ]
                updated_placement_ids = await placement_repo.bulk_apply_backend_report(
                    [item.model_dump(mode="python") for item in bulk_items]
                )

                for i, msg, event, node_id in new_items:
                    pid = UUID(event.placement_id)
                    if pid in updated_placement_ids:
                        state = PlacementAppliedState(event.applied_state.value)
                        if state == PlacementAppliedState.applied:
                            ack_statuses[i] = TransportReportStatus.applied
                        elif state == PlacementAppliedState.error:
                            ack_statuses[i] = TransportReportStatus.error
                        else:
                            ack_statuses[i] = TransportReportStatus.pending
                    else:
                        ack_statuses[i] = TransportReportStatus.skipped_stale
                    ack_flags[i] = True

            state_repo = NodeTransportStateRepository(session)
            last_events: dict[UUID, tuple[str, datetime]] = {}
            for _, _, event, node_id in valid:
                last_events[node_id] = (event.event_id, event.emitted_at)
            for nid, (eid, at) in last_events.items():
                await state_repo.touch_result(node_id=nid, event_id=eid, at=at)

            await self._finish_session(session)

        for i, _, event, _ in parsed:
            if ack_statuses[i] is not None:
                await self._publish_result_ack(
                    node_id=event.node_id,
                    result_event=event,
                    status=ack_statuses[i],
                )

        return ack_flags

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
                chunked = self._chunk_items(snapshot_items, chunk_size=NODE_AGENT_SNAPSHOT_CHUNK_SIZE)
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
                return await self._publish_sync_report_ack(
                    node_id=event.node_id,
                    ack_event=SyncReportAckEvent(
                        event_id=event.event_id,
                        node_id=event.node_id,
                        emitted_at=datetime.now(timezone.utc),
                        status=SyncReportAckStatus.skipped,
                        error="unknown_node",
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
            msg_id=f"sync-report-ack:{ack_event.event_id}:{ack_event.emitted_at.isoformat()}",
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
    def _snapshot_request_event_id(event: SnapshotRequestEvent) -> str:
        return (
            f"snapshot-request:{event.node_id}:{event.reason.value}:"
            f"{event.requested_at.isoformat()}:{event.known_snapshot_id or ''}"
        )

    @staticmethod
    def _chunk_items(items: list[PlacementCommandEvent], *, chunk_size: int) -> list[list[PlacementCommandEvent]]:
        return [items[idx: idx + chunk_size] for idx in range(0, len(items), chunk_size)]
