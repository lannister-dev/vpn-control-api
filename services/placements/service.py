from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import (
    PlacementApplyResultIn,
    PlacementApplyStatus,
    PlacementMigrateBackendIn,
    PlacementMigrateBackendOut,
    PlacementAppliedState,
    PlacementDesiredState,
    UserPlacementOut,
    UserPlacementUpsertIn,
)
from services.vpn.keys.repository import VpnKeyRepository
from services.routing.service import RoutingService
from shared.database.session import AsyncDatabase
from services.placements.transport import NodeAgentPlacementTransport
from shared.monitoring.metrics import NODE_PLACEMENT_REPORT_TOTAL


class UserPlacementService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.placement_repository = UserPlacementRepository(session)
        self.key_repository = VpnKeyRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.routing_service = RoutingService(session)
        self.node_agent_transport = NodeAgentPlacementTransport(session)

    async def upsert(self, payload: UserPlacementUpsertIn) -> UserPlacementOut:
        key = await self.key_repository.get_by_id(payload.key_id)
        if not key:
            raise HTTPException(status_code=404, detail="Key not found")

        backend = await self.node_repository.get_by_id(payload.backend_node_id)
        if not backend:
            raise HTTPException(status_code=404, detail="Backend node not found")

        placement = await self.placement_repository.upsert_set_pending(
            key_id=payload.key_id,
            backend_node_id=payload.backend_node_id,
            desired_state=payload.desired_state.value,
            sticky_until=payload.sticky_until,
            last_migration_reason=payload.last_migration_reason,
        )
        if not placement:
            raise HTTPException(status_code=500, detail="Failed to upsert placement")
        await self.node_agent_transport.enqueue_for_placement_ids([placement.id])
        return UserPlacementOut.model_validate(placement)

    async def migrate_backend(
            self,
            payload: PlacementMigrateBackendIn,
    ) -> PlacementMigrateBackendOut:
        if payload.target_backend_id is not None and payload.source_backend_id == payload.target_backend_id:
            raise HTTPException(status_code=400, detail="source_backend_id and target_backend_id must differ")

        source = await self.node_repository.get_by_id(payload.source_backend_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source node not found")

        target: VpnNode | None = None
        if payload.target_backend_id is not None:
            target = await self.node_repository.get_by_id(payload.target_backend_id)
            if not target:
                raise HTTPException(status_code=404, detail="Target node not found")
        else:
            candidates = await self.routing_service.select_nodes(
                preferred_region=source.region,
                exclude_node_ids=[source.id],
            )
            if not candidates:
                raise HTTPException(status_code=503, detail="No eligible target node available")
            target = candidates[0]

        if target is None:
            raise HTTPException(status_code=503, detail="No eligible target node available")
        if not target.is_active or not target.is_enabled or target.is_draining:
            raise HTTPException(status_code=409, detail="Target node is not eligible")

        placements = await self.placement_repository.list_active(backend_node_id=payload.source_backend_id)
        active_placements = [p for p in placements if p.desired_state == PlacementDesiredState.active.value]

        now = datetime.now(timezone.utc)
        if active_placements:
            _migrated, target_placement_ids = await self.placement_repository.bulk_migrate_backend(
                placement_ids=[placement.id for placement in active_placements],
                target_backend_id=target.id,
                last_migration_reason=payload.last_migration_reason,
                updated_at=now,
            )
            if target_placement_ids:
                await self.node_agent_transport.enqueue_for_placement_ids(
                    target_placement_ids
                )

        return PlacementMigrateBackendOut(
            source_backend_id=payload.source_backend_id,
            target_backend_id=target.id,
            migrated_count=len(active_placements),
        )

    async def list_placements(
            self,
            *,
            backend_node_id: UUID | None = None,
            limit: int = 200,
    ) -> list[UserPlacementOut]:
        rows = await self.placement_repository.list_active(
            backend_node_id=backend_node_id,
            limit=limit,
        )
        return [UserPlacementOut.model_validate(r) for r in rows]

    async def list_by_key_id(self, key_id: UUID) -> list[UserPlacementOut]:
        rows = await self.placement_repository.list_by_key_id(
            key_id=key_id,
            active_only=True,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Placement not found")
        return [UserPlacementOut.model_validate(row) for row in rows]


class PlacementApplyService:
    def __init__(self, session: AsyncSession):
        self.placement_repository = UserPlacementRepository(session)

    async def apply_result(
            self,
            *,
            node: VpnNode,
            placement_id: UUID,
            payload: PlacementApplyResultIn,
    ) -> PlacementApplyStatus:
        now = datetime.now(timezone.utc)
        applied_state_value: str = payload.applied_state
        updated_rows = await self.placement_repository.apply_backend_report(
            placement_id=placement_id,
            expected_op_version=payload.op_version,
            applied_state=applied_state_value,
            applied_version=payload.op_version,
            updated_at=now,
            reporter_backend_id=node.id,
        )
        if updated_rows == 0:
            NODE_PLACEMENT_REPORT_TOTAL.labels(status="skipped_stale").inc()
            return "skipped_stale"
        if payload.applied_state == PlacementAppliedState.applied:
            NODE_PLACEMENT_REPORT_TOTAL.labels(status="applied").inc()
            return "applied"
        if payload.applied_state == PlacementAppliedState.error:
            NODE_PLACEMENT_REPORT_TOTAL.labels(status="error").inc()
            return "error"
        NODE_PLACEMENT_REPORT_TOTAL.labels(status="pending").inc()
        return "pending"


def get_user_placement_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> UserPlacementService:
    return UserPlacementService(session)
