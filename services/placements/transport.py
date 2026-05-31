from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.entry.models import EntryBackendAssignment
from services.nodes.agent.repository import NodeTransportOutboxRepository
from services.nodes.agent.schemas import (
    AgentSubjects,
    OutboxEnqueueItem,
    PlacementCommandPayload,
    TransportDesiredState,
    TransportProtocol,
    TransportVpnTransport,
)
from services.placements.models import UserPlacement
from services.placements.repository import UserPlacementRepository
from services.vpn.keys.models import VpnKey


class NodeAgentPlacementTransport:
    def __init__(self, session: AsyncSession):
        settings = get_settings().nats
        self._placement_repository = UserPlacementRepository(session)
        self._outbox_repository = NodeTransportOutboxRepository(session)
        self._subjects = AgentSubjects(
            command_prefix=settings.js_command_subject_prefix,
            result_prefix=settings.js_result_subject_prefix,
            snapshot_prefix=settings.js_snapshot_subject_prefix,
            heartbeat_prefix=settings.js_heartbeat_subject_prefix,
            sync_report_prefix=settings.js_sync_report_subject_prefix,
        )

    async def enqueue_for_placement_ids(self, placement_ids: list[UUID]) -> None:
        rows = await self._placement_repository.list_transport_rows_by_placement_ids(
            placement_ids=placement_ids
        )
        if not rows:
            return
        backend_ids = {placement.backend_node_id for placement, _ in rows}
        entries_by_backend = await self._load_entries_for_backends(backend_ids)
        items: list[OutboxEnqueueItem] = []
        for placement, key in rows:
            backend_payload = self._build_command_payload(placement=placement, key=key)
            items.append(
                OutboxEnqueueItem(
                    node_id=backend_payload.node_id,
                    event_type="placement_command",
                    aggregate_id=backend_payload.placement_id,
                    op_version=backend_payload.op_version,
                    subject=self._subjects.placement_command(str(backend_payload.node_id)),
                    payload=backend_payload.model_dump(mode="json"),
                    message_id=f"placement-command:{backend_payload.placement_id}:{backend_payload.op_version}",
                    status="pending",
                )
            )
            for entry_node_id in entries_by_backend.get(placement.backend_node_id, ()):
                entry_payload = self._build_command_payload(
                    placement=placement,
                    key=key,
                    override_node_id=entry_node_id,
                )
                items.append(
                    OutboxEnqueueItem(
                        node_id=entry_payload.node_id,
                        event_type="placement_command",
                        aggregate_id=entry_payload.placement_id,
                        op_version=entry_payload.op_version,
                        subject=self._subjects.placement_command(str(entry_payload.node_id)),
                        payload=entry_payload.model_dump(mode="json"),
                        message_id=f"placement-command:{entry_payload.placement_id}:{entry_payload.op_version}:{entry_node_id}",
                        status="pending",
                    )
                )
        await self._outbox_repository.enqueue_many(items)

    async def _load_entries_for_backends(
        self,
        backend_ids: set[UUID],
    ) -> dict[UUID, list[UUID]]:
        if not backend_ids:
            return {}
        session = self._placement_repository.session
        stmt = (
            select(EntryBackendAssignment.backend_node_id, EntryBackendAssignment.entry_node_id)
            .where(EntryBackendAssignment.backend_node_id.in_(backend_ids))
            .where(EntryBackendAssignment.enabled.is_(True))
        )
        result = await session.execute(stmt)
        mapping: dict[UUID, list[UUID]] = defaultdict(list)
        for backend_id, entry_id in result.all():
            mapping[backend_id].append(entry_id)
        return mapping

    async def enqueue_for_key_state(
        self,
        *,
        key_id: UUID,
        desired_state: str,
        backend_node_ids: list[UUID] | None = None,
    ) -> None:
        placement_ids = await self._placement_repository.list_active_ids_for_key(
            key_id=key_id,
            desired_state=desired_state,
            backend_node_ids=backend_node_ids,
        )
        await self.enqueue_for_placement_ids(placement_ids)

    async def list_command_payloads_for_backend(
        self,
        *,
        backend_node_id: UUID,
    ) -> list[PlacementCommandPayload]:
        rows = await self._placement_repository.list_transport_rows_for_backend(
            backend_node_id=backend_node_id
        )
        return [self._build_command_payload(placement=placement, key=key) for placement, key in rows]

    async def list_command_payloads_for_entry(
        self,
        *,
        entry_node_id: UUID,
    ) -> list[PlacementCommandPayload]:
        rows = await self._placement_repository.list_transport_rows_for_entry(
            entry_node_id=entry_node_id
        )
        return [
            self._build_command_payload(placement=placement, key=key, override_node_id=entry_node_id)
            for placement, key in rows
        ]

    @staticmethod
    def _build_command_payload(
        *,
        placement: UserPlacement,
        key: VpnKey,
        override_node_id: UUID | None = None,
    ) -> PlacementCommandPayload:
        return PlacementCommandPayload(
            placement_id=placement.id,
            key_id=placement.key_id,
            node_id=override_node_id if override_node_id is not None else placement.backend_node_id,
            backend_node_id=placement.backend_node_id,
            op_version=placement.op_version,
            desired_state=TransportDesiredState(placement.desired_state),
            protocol=TransportProtocol(key.protocol),
            transport=TransportVpnTransport(key.transport),
            client_id=key.client_id,
            is_revoked=bool(key.is_revoked),
            valid_until=key.valid_until,
            updated_at=placement.updated_at,
            entry_routing_override_backend_tag=key.entry_routing_override_backend_tag,
        )
