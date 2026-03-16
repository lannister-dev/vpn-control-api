from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.placements.model import UserPlacement
from services.placements.repository import UserPlacementRepository
from services.vpn.keys.models import VpnKey
from services.nodes.agent.repository import NodeTransportOutboxRepository
from services.nodes.agent.schemas import (
    AgentSubjects,
    PlacementCommandPayload,
    TransportDesiredState,
    TransportProtocol,
    TransportVpnTransport,
)


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
        payloads = [self._build_command_payload(placement=placement, key=key) for placement, key in rows]
        if not payloads:
            return
        await self._outbox_repository.enqueue_many(
            [
                {
                    "node_id": payload.node_id,
                    "event_type": "placement_command",
                    "aggregate_id": payload.placement_id,
                    "op_version": payload.op_version,
                    "subject": self._subjects.placement_command(str(payload.node_id)),
                    "payload": payload.model_dump(mode="json"),
                    "message_id": f"placement-command:{payload.placement_id}:{payload.op_version}",
                    "status": "pending",
                }
                for payload in payloads
            ]
        )

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

    @staticmethod
    def _build_command_payload(
        *,
        placement: UserPlacement,
        key: VpnKey,
    ) -> PlacementCommandPayload:
        return PlacementCommandPayload(
            placement_id=placement.id,
            key_id=placement.key_id,
            node_id=placement.backend_node_id,
            backend_node_id=placement.backend_node_id,
            op_version=placement.op_version,
            desired_state=TransportDesiredState(placement.desired_state),
            protocol=TransportProtocol(key.protocol),
            transport=TransportVpnTransport(key.transport),
            client_id=key.client_id,
            is_revoked=bool(key.is_revoked),
            valid_until=key.valid_until,
            updated_at=placement.updated_at,
        )
