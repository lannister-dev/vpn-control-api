from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.backend_peers.repository import BackendPeerRepository
from services.nodes.models import VpnNode
from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.nodes.schemas import NodeRole
from services.placements.model import UserPlacement
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import (
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
        self.backend_peer_repository = BackendPeerRepository(session)
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
        if self._node_role(backend, default=NodeRole.backend.value) != NodeRole.backend.value:
            raise HTTPException(status_code=409, detail="Node role must be backend")

        if payload.gateway_node_id is not None:
            gateway = await self.node_repository.get_by_id(payload.gateway_node_id)
            if not gateway:
                raise HTTPException(status_code=404, detail="Gateway node not found")
            if self._node_role(gateway, default=NodeRole.gateway.value) != NodeRole.gateway.value:
                raise HTTPException(status_code=409, detail="Node role must be gateway")
            await self.backend_peer_repository.ensure_active_pair(
                backend_node_id=payload.backend_node_id,
                gateway_node_id=payload.gateway_node_id,
            )

        placement = await self.placement_repository.upsert_set_pending(
            key_id=payload.key_id,
            backend_node_id=payload.backend_node_id,
            gateway_node_id=payload.gateway_node_id,
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
            raise HTTPException(status_code=404, detail="Source backend node not found")
        if self._node_role(source, default=NodeRole.backend.value) != NodeRole.backend.value:
            raise HTTPException(status_code=409, detail="Source node role must be backend")

        target: VpnNode | None = None
        if payload.target_backend_id is not None:
            target = await self.node_repository.get_by_id(payload.target_backend_id)
            if not target:
                raise HTTPException(status_code=404, detail="Target backend node not found")
        else:
            candidates = await self.routing_service.select_nodes(
                preferred_region=source.region,
                exclude_node_ids=[source.id],
                role=NodeRole.backend.value,
            )
            if not candidates:
                raise HTTPException(status_code=503, detail="No eligible target backend node available")
            target = candidates[0]

        if target is None:
            raise HTTPException(status_code=503, detail="No eligible target backend node available")
        if self._node_role(target, default=NodeRole.backend.value) != NodeRole.backend.value:
            raise HTTPException(status_code=409, detail="Target node role must be backend")
        if not target.is_active or not target.is_enabled or target.is_draining:
            raise HTTPException(status_code=409, detail="Target backend node is not eligible")

        placements = await self.placement_repository.list_active(backend_node_id=payload.source_backend_id)
        active_placements = [p for p in placements if p.desired_state == PlacementDesiredState.active.value]

        gateway_ids = {p.gateway_node_id for p in active_placements if p.gateway_node_id is not None}
        gateway_ids.update(await self._list_active_gateway_ids())
        for gateway_id in gateway_ids:
            await self.backend_peer_repository.ensure_active_pair(
                backend_node_id=target.id,
                gateway_node_id=gateway_id,
            )

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

    @staticmethod
    def _node_role(node: VpnNode, *, default: str) -> str:
        role = getattr(node, "role", None)
        if isinstance(role, str):
            return role
        return default

    async def _list_active_gateway_ids(self) -> set[UUID]:
        rows = await self.node_repository.list_public(role=NodeRole.gateway.value)
        if not isinstance(rows, list):
            return set()

        gateway_ids: set[UUID] = set()
        for row in rows:
            if not getattr(row, "is_active", True):
                continue
            if not getattr(row, "is_enabled", True):
                continue
            if getattr(row, "is_draining", False):
                continue
            public_domain = (getattr(row, "public_domain", "") or "").strip()
            if not public_domain:
                continue
            gateway_ids.add(row.id)
        return gateway_ids

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

    async def get_by_key_id(self, key_id: UUID) -> UserPlacementOut:
        row = await self.placement_repository.get_by_key_id(key_id)
        if not row:
            raise HTTPException(status_code=404, detail="Placement not found")
        return UserPlacementOut.model_validate(row)


class PlacementAgentService:
    def __init__(self, session: AsyncSession):
        self.placement_repository = UserPlacementRepository(session)
        self.node_agent_state_repository = NodeAgentStateRepository(session)

    async def get_page_for_gateway(
            self,
            *,
            node: VpnNode,
            cursor: str | None,
            limit: int,
    ) -> PlacementPageOut:
        if getattr(node, "role", None) != NodeRole.gateway.value:
            raise HTTPException(status_code=403, detail="Node role must be gateway")
        parsed: tuple[int, UUID] | None = None
        if cursor:
            try:
                op_s, pid_s = cursor.split(":", 1)
                parsed = (int(op_s), UUID(pid_s))
            except Exception as exc:
                raise ValueError(f"Invalid cursor format: {cursor!r}") from exc

        rows = await self.placement_repository.list_for_gateway_with_keys_page(
            gateway_node_id=node.id,
            cursor=parsed,
            limit=limit,
            include_unbound=True,
        )
        items = self._build_items(rows)
        next_cursor = None
        if items:
            last = items[-1]
            next_cursor = f"{last.op_version}:{last.id}"
        return PlacementPageOut(items=items, next_cursor=next_cursor)

    async def report_for_gateway(
            self,
            *,
            node: VpnNode,
            placement_id: UUID,
            payload: PlacementReportIn,
    ) -> PlacementReportStatus:
        if getattr(node, "role", None) != NodeRole.gateway.value:
            raise HTTPException(status_code=403, detail="Node role must be gateway")
        placement = await self.placement_repository.get_by_id(placement_id)
        if not placement:
            raise HTTPException(status_code=404, detail="Placement not found")

        if placement.gateway_node_id is not None and placement.gateway_node_id != node.id:
            raise HTTPException(status_code=403, detail="Placement does not belong to this gateway")

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
        updated_rows = await self.placement_repository.apply_gateway_report(
            placement_id=placement_id,
            expected_op_version=payload.op_version,
            applied_state=applied_state_value,
            applied_version=payload.op_version,
            updated_at=now,
            reporter_gateway_id=node.id,
        )
        if updated_rows == 0:
            NODE_PLACEMENT_REPORT_TOTAL.labels(status="skipped_stale").inc()
            return "skipped_stale"
        if payload.applied_state == PlacementAppliedState.applied:
            await self.node_agent_state_repository.touch_last_sync(node_id=node.id, at=now)
            NODE_PLACEMENT_REPORT_TOTAL.labels(status="applied").inc()
            return "applied"
        if payload.applied_state == PlacementAppliedState.error:
            NODE_PLACEMENT_REPORT_TOTAL.labels(status="error").inc()
            return "error"
        NODE_PLACEMENT_REPORT_TOTAL.labels(status="pending").inc()
        return "pending"

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
                    gateway_node_id=placement.gateway_node_id,
                    protocol=VpnProtocol(key.protocol),
                    client_id=key.client_id,
                    transport=VpnTransport(key.transport),
                    valid_until=key.valid_until,
                    is_revoked=key.is_revoked,
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
