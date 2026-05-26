from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from uuid import uuid4

from sqlalchemy import select

from services.config import NatsConfig
from services.entry.models import EntryBackendAssignment
from services.nodes.agent.constants import NODE_AGENT_SNAPSHOT_CHUNK_SIZE
from services.nodes.agent.repository import NodeTransportStateRepository
from services.nodes.agent.schemas import (
    AgentSubjects,
    PlacementCommandEvent,
    SnapshotChunkEvent,
    UpstreamChangedPayload,
)
from services.nodes.models import VpnNode
from services.placements.transport import NodeAgentPlacementTransport
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient


class AdminSnapshotPublisher:
    def __init__(self, *, nats_client: NatsClient, config: NatsConfig):
        self._nats = nats_client
        self._config = config
        self._subjects = AgentSubjects(
            command_prefix=config.js_command_subject_prefix,
            result_prefix=config.js_result_subject_prefix,
            snapshot_prefix=config.js_snapshot_subject_prefix,
            heartbeat_prefix=config.js_heartbeat_subject_prefix,
            sync_report_prefix=config.js_sync_report_subject_prefix,
        )

    async def execute(self, *, node_id: UUID, reason: str = "admin_requested") -> tuple[int, str]:
        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            role_row = await session.execute(
                select(VpnNode.role).where(VpnNode.id == node_id)
            )
            role = role_row.scalar_one_or_none() or "backend"
            transport = NodeAgentPlacementTransport(session)
            if role in ("entry", "whitelist_entry"):
                commands = await transport.list_command_payloads_for_entry(entry_node_id=node_id)
            else:
                commands = await transport.list_command_payloads_for_backend(backend_node_id=node_id)
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
                await self._publish_chunk(
                    node_id=str(node_id),
                    snapshot_id=reserved_snapshot_id,
                    epoch=epoch,
                    chunk_index=0,
                    is_last_chunk=True,
                    items=[],
                )
            else:
                chunks = [
                    snapshot_items[i:i + NODE_AGENT_SNAPSHOT_CHUNK_SIZE]
                    for i in range(0, len(snapshot_items), NODE_AGENT_SNAPSHOT_CHUNK_SIZE)
                ]
                for index, chunk in enumerate(chunks):
                    is_last = index == len(chunks) - 1
                    for item in chunk:
                        item.snapshot_complete = is_last
                    await self._publish_chunk(
                        node_id=str(node_id),
                        snapshot_id=reserved_snapshot_id,
                        epoch=epoch,
                        chunk_index=index,
                        is_last_chunk=is_last,
                        items=chunk,
                    )
            if role in ("entry", "whitelist_entry"):
                await self._publish_upstreams_for_entry(
                    session=session,
                    entry_node_id=node_id,
                    now=now,
                )
            await session.commit()
            return epoch, reserved_snapshot_id

    async def _publish_upstreams_for_entry(
        self,
        *,
        session,
        entry_node_id: UUID,
        now: datetime,
    ) -> None:
        rows = await session.execute(
            select(VpnNode)
            .join(
                EntryBackendAssignment,
                EntryBackendAssignment.backend_node_id == VpnNode.id,
            )
            .where(EntryBackendAssignment.entry_node_id == entry_node_id)
            .where(EntryBackendAssignment.enabled.is_(True))
        )
        backends = rows.scalars().all()
        for backend in backends:
            event = UpstreamChangedPayload(
                event_id=str(uuid4()),
                node_id=str(entry_node_id),
                emitted_at=now,
                upstream_node_id=str(backend.id),
                upstream_public_domain=str(backend.public_domain or ""),
                upstream_reality_ip=getattr(backend, "reality_ip", None),
            )
            await self._nats.publish_jetstream(
                subject=self._subjects.upstream_changed(str(entry_node_id)),
                payload=event.model_dump(mode="json"),
                msg_id=f"upstream-snapshot:{entry_node_id}:{backend.id}:{now.isoformat()}",
            )

    async def _publish_chunk(
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
