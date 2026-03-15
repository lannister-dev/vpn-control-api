from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import VpnNode
from services.nodes.repository import VpnNodeRepository
from services.placements.model import UserPlacement
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import (
    PlacementBatchReportIn,
    PlacementBatchReportItemOut,
    PlacementBatchReportOut,
    PlacementMigrateBackendIn,
    PlacementMigrateBackendOut,
    PlacementAppliedState,
    PlacementAssignmentOut,
    PlacementDesiredState,
    PlacementPageOut,
    PlacementReportIn,
    PlacementReportStatus,
    UserPlacementOut,
    UserPlacementUpsertIn,
)
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.keys.models import VpnKey
from services.vpn.keys.schemas import VpnProtocol, VpnTransport
from services.routing.service import RoutingService
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import NODE_PLACEMENT_REPORT_TOTAL


class UserPlacementService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.placement_repository = UserPlacementRepository(session)
        self.key_repository = VpnKeyRepository(session)
        self.node_repository = VpnNodeRepository(session)
        self.routing_service = RoutingService(session)

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
            await self.placement_repository.bulk_migrate_backend(
                placement_ids=[placement.id for placement in active_placements],
                target_backend_id=target.id,
                last_migration_reason=payload.last_migration_reason,
                updated_at=now,
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


class PlacementAgentService:
    def __init__(self, session: AsyncSession):
        self.placement_repository = UserPlacementRepository(session)

    async def get_page_for_backend(
            self,
            *,
            node: VpnNode,
            cursor: str | None,
            limit: int,
    ) -> PlacementPageOut:
        parsed: tuple[datetime, UUID] | None = None
        if cursor:
            try:
                updated_ms_s, pid_s = cursor.split(":", 1)
                updated_at = datetime.fromtimestamp(int(updated_ms_s) / 1000, tz=timezone.utc)
                parsed = (updated_at, UUID(pid_s))
            except Exception as exc:
                raise ValueError(f"Invalid cursor format: {cursor!r}") from exc

        rows = await self.placement_repository.list_for_backend_with_keys_page(
            backend_node_id=node.id,
            cursor=parsed,
            limit=limit,
        )
        items = self._build_items(rows)
        next_cursor = None
        if items:
            last = items[-1]
            updated_at = last.updated_at
            if updated_at is None:
                raise RuntimeError("placement page item missing updated_at")
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            else:
                updated_at = updated_at.astimezone(timezone.utc)
            next_cursor = f"{int(updated_at.timestamp() * 1000)}:{last.id}"
        return PlacementPageOut(items=items, next_cursor=next_cursor)

    async def report_for_backend(
            self,
            *,
            node: VpnNode,
            placement_id: UUID,
            payload: PlacementReportIn,
    ) -> PlacementReportStatus:
        placement = await self.placement_repository.get_by_id(placement_id)
        if not placement:
            raise HTTPException(status_code=404, detail="Placement not found")

        if placement.backend_node_id != node.id:
            raise HTTPException(status_code=403, detail="Placement does not belong to this backend")

        if payload.op_version != placement.op_version:
            NODE_PLACEMENT_REPORT_TOTAL.labels(status="skipped_stale").inc()
            return "skipped_stale"

        if (
                placement.applied_version == payload.op_version
                and placement.applied_state == payload.applied_state
        ):
            NODE_PLACEMENT_REPORT_TOTAL.labels(status="skipped_idempotent").inc()
            return "skipped_idempotent"

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

    async def report_batch_for_backend(
            self,
            *,
            node: VpnNode,
            payload: PlacementBatchReportIn,
    ) -> PlacementBatchReportOut:
        if not payload.items:
            return PlacementBatchReportOut(items=[])

        placement_ids = [item.placement_id for item in payload.items]
        placements = await self.placement_repository.list_by_ids_for_backend(
            placement_ids=placement_ids,
            backend_node_id=node.id,
        )
        placement_by_id = {placement.id: placement for placement in placements}

        items_out: list[PlacementBatchReportItemOut] = []
        to_update: list[tuple[UUID, int, str, int]] = []
        pending_ids: list[UUID] = []
        pending_status_by_id: dict[UUID, str] = {}

        for item in payload.items:
            placement = placement_by_id.get(item.placement_id)
            if placement is None or item.op_version != placement.op_version:
                status = "skipped_stale"
            elif (
                    placement.applied_version == item.op_version
                    and placement.applied_state == item.applied_state
            ):
                status = "skipped_idempotent"
            else:
                status = ""
                pending_ids.append(item.placement_id)
                pending_status_by_id[item.placement_id] = item.applied_state.value
                to_update.append(
                    (
                        item.placement_id,
                        item.op_version,
                        item.applied_state.value,
                        item.op_version,
                    )
                )

            if status:
                NODE_PLACEMENT_REPORT_TOTAL.labels(status=status).inc()
                items_out.append(
                    PlacementBatchReportItemOut(
                        placement_id=item.placement_id,
                        status=status,
                    )
                )

        updated_ids = await self.placement_repository.apply_backend_reports_batch(
            reports=to_update,
            updated_at=datetime.now(timezone.utc),
            reporter_backend_id=node.id,
        )

        for placement_id in pending_ids:
            if placement_id in updated_ids:
                status = pending_status_by_id[placement_id]
            else:
                status = "skipped_stale"
            NODE_PLACEMENT_REPORT_TOTAL.labels(status=status).inc()
            items_out.append(
                PlacementBatchReportItemOut(
                    placement_id=placement_id,
                    status=status,
                )
            )

        status_by_id = {item.placement_id: item for item in items_out}
        ordered = [status_by_id[item.placement_id] for item in payload.items]
        return PlacementBatchReportOut(items=ordered)

    def _build_items(
            self,
            rows: Sequence[tuple[UserPlacement, VpnKey, VpnNode]]
    ) -> list[PlacementAssignmentOut]:
        now = datetime.now(timezone.utc)
        out: list[PlacementAssignmentOut] = []

        for placement, key, backend_node in rows:
            desired = PlacementDesiredState(placement.desired_state)

            if key.is_revoked:
                desired = PlacementDesiredState.inactive
            elif key.valid_until is not None:
                vu = key.valid_until
                if vu.tzinfo is None:
                    vu = vu.replace(tzinfo=timezone.utc)
                if vu <= now:
                    desired = PlacementDesiredState.inactive

            out.append(
                PlacementAssignmentOut(
                    id=placement.id,
                    key_id=placement.key_id,
                    op_version=placement.op_version,
                    desired_state=desired,
                    applied_state=PlacementAppliedState(placement.applied_state),
                    applied_version=placement.applied_version,
                    backend_node_id=placement.backend_node_id,
                    protocol=VpnProtocol(key.protocol),
                    client_id=key.client_id,
                    transport=VpnTransport(key.transport),
                    valid_until=key.valid_until,
                    is_revoked=key.is_revoked,
                    updated_at=placement.updated_at,
                    backend_internal_wg_ip=backend_node.internal_wg_ip,
                    backend_xray_api_port=backend_node.xray_api_port,
                )
            )
        return out


def get_user_placement_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> UserPlacementService:
    return UserPlacementService(session)


def get_placement_agent_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> PlacementAgentService:
    return PlacementAgentService(session)
