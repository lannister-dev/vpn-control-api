from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.nodes.models import NodeAgentState, VpnNode
from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.routing.service import RoutingService
from shared.monitoring.metrics import (
    NODE_STATE_FRESHNESS_SECONDS,
    PLACEMENT_ACTIVE_BY_BACKEND,
    PLACEMENT_AUTO_HEAL_TOTAL,
    PLACEMENT_ORPHAN_ACTIVE_TOTAL,
)


@dataclass(slots=True)
class NodeAutoHealTickOut:
    processed_nodes: int = 0
    drained_nodes: int = 0
    migrated_nodes: int = 0
    migrated_placements: int = 0
    skipped_nodes: int = 0
    undrained_nodes: int = 0
    orphan_active_placements: int = 0


class NodePlacementAutoHealService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        stale_after_sec: int,
        max_nodes: int,
        auto_undrain_enabled: bool,
    ):
        self.node_repository = VpnNodeRepository(session)
        self.node_agent_state_repository = NodeAgentStateRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.routing_service = RoutingService(session)
        self.stale_after_sec = max(30, int(stale_after_sec))
        self.max_nodes = min(500, max(1, int(max_nodes)))
        self.auto_undrain_enabled = bool(auto_undrain_enabled)

    async def run_once(self) -> NodeAutoHealTickOut:
        now = datetime.now(timezone.utc)
        out = NodeAutoHealTickOut()

        await self._observe_node_freshness(now=now)

        desired_active_counts = await self.placement_repository.count_desired_active_by_backend_node()
        for node_id, active_count in desired_active_counts.items():
            PLACEMENT_ACTIVE_BY_BACKEND.labels(node_id=str(node_id)).set(active_count)
        if not desired_active_counts:
            PLACEMENT_ORPHAN_ACTIVE_TOTAL.set(0)
            if self.auto_undrain_enabled:
                out.undrained_nodes = await self._recover_draining_nodes(
                    now=now,
                    desired_active_counts={},
                )
            return out

        node_ids = list(desired_active_counts.keys())
        nodes = await self.node_repository.list_by_ids(node_ids)
        states = await self.node_agent_state_repository.list_by_node_ids(node_ids)
        nodes_by_id = {node.id: node for node in nodes}
        states_by_node_id = {state.node_id: state for state in states}

        source_ids_ordered = sorted(
            node_ids,
            key=lambda node_id: desired_active_counts.get(node_id, 0),
            reverse=True,
        )

        orphan_total = 0
        for source_node_id in source_ids_ordered:
            if out.processed_nodes >= self.max_nodes:
                break

            active_count = desired_active_counts.get(source_node_id, 0)
            if active_count <= 0:
                continue

            node = nodes_by_id.get(source_node_id)
            state = states_by_node_id.get(source_node_id)
            reason = self._unavailability_reason(node=node, state=state, now=now)
            if reason is None:
                continue

            out.processed_nodes += 1
            orphan_total += active_count
            PLACEMENT_AUTO_HEAL_TOTAL.labels(action="evaluate", result=reason).inc()

            if node is not None and not node.is_draining:
                await self.node_repository.update_by_id(node.id, {"is_draining": True})
                out.drained_nodes += 1
                PLACEMENT_AUTO_HEAL_TOTAL.labels(action="drain", result="ok").inc()

            target = await self._select_target_backend(
                source_node=node,
                source_node_id=source_node_id,
            )
            if target is None:
                out.skipped_nodes += 1
                PLACEMENT_AUTO_HEAL_TOTAL.labels(action="migrate", result="no_target").inc()
                continue

            migrated = await self._migrate_active_placements(
                source_node_id=source_node_id,
                target_backend_id=target.id,
                updated_at=now,
            )
            if migrated <= 0:
                out.skipped_nodes += 1
                PLACEMENT_AUTO_HEAL_TOTAL.labels(action="migrate", result="no_active").inc()
                continue

            out.migrated_nodes += 1
            out.migrated_placements += migrated
            PLACEMENT_AUTO_HEAL_TOTAL.labels(action="migrate", result="ok").inc()

        out.orphan_active_placements = orphan_total
        PLACEMENT_ORPHAN_ACTIVE_TOTAL.set(orphan_total)
        if self.auto_undrain_enabled:
            out.undrained_nodes = await self._recover_draining_nodes(
                now=now,
                desired_active_counts=desired_active_counts,
            )
        return out

    async def _observe_node_freshness(self, *, now: datetime) -> None:
        rows = await self.node_repository.list_active_with_agent_state()
        for node, state in rows:
            freshness = self._freshness_seconds(state=state, now=now)
            NODE_STATE_FRESHNESS_SECONDS.labels(node_id=str(node.id)).set(
                freshness if freshness is not None else -1.0
            )

    async def _recover_draining_nodes(
        self,
        *,
        now: datetime,
        desired_active_counts: dict[UUID, int],
    ) -> int:
        rows = await self.node_repository.list_active_with_agent_state()
        undrained = 0
        for node, state in rows:
            if not node.is_active or not node.is_enabled or not node.is_draining:
                continue
            if desired_active_counts.get(node.id, 0) > 0:
                continue
            if state is None or not state.is_healthy:
                continue
            freshness = self._freshness_seconds(state=state, now=now)
            if freshness is None or freshness > self.stale_after_sec:
                continue
            await self.node_repository.update_by_id(node.id, {"is_draining": False})
            undrained += 1
            PLACEMENT_AUTO_HEAL_TOTAL.labels(action="undrain", result="ok").inc()
        return undrained

    async def _select_target_backend(
        self,
        *,
        source_node: VpnNode | None,
        source_node_id: UUID,
    ) -> VpnNode | None:
        preferred_region = source_node.region if source_node is not None else None
        candidates = await self.routing_service.select_nodes(
            preferred_region=preferred_region,
            exclude_node_ids=[source_node_id],
        )
        return candidates[0] if candidates else None

    async def _migrate_active_placements(
        self,
        *,
        source_node_id: UUID,
        target_backend_id: UUID,
        updated_at: datetime,
    ) -> int:
        placements = await self.placement_repository.list_active(backend_node_id=source_node_id)
        active_ids = [
            placement.id
            for placement in placements
            if placement.desired_state == PlacementDesiredState.active.value
        ]
        if not active_ids:
            return 0
        return await self.placement_repository.bulk_migrate_backend(
            placement_ids=active_ids,
            target_backend_id=target_backend_id,
            last_migration_reason="node_auto_heal",
            updated_at=updated_at,
        )

    def _unavailability_reason(
        self,
        *,
        node: VpnNode | None,
        state: NodeAgentState | None,
        now: datetime,
    ) -> str | None:
        if node is None:
            return "missing_node"
        if not node.is_active:
            return "node_inactive"
        if not node.is_enabled:
            return "node_disabled"
        if node.is_draining:
            return "node_draining"
        if state is None:
            return "state_missing"
        if not state.is_healthy:
            return "state_unhealthy"
        freshness = self._freshness_seconds(state=state, now=now)
        if freshness is None:
            return "state_missing_last_seen"
        if freshness > self.stale_after_sec:
            return "state_stale"
        return None

    @staticmethod
    def _freshness_seconds(*, state: NodeAgentState | None, now: datetime) -> float | None:
        if state is None:
            return None
        last_seen = state.last_seen_at
        if last_seen is None:
            return None
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        else:
            last_seen = last_seen.astimezone(timezone.utc)
        return max(0.0, (now - last_seen).total_seconds())
