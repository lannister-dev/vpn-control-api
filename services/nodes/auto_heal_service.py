from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.nodes.models import NodeAgentState, VpnNode
from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.nodes.schemas import NodeHeartbeatMeta
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.probe.repository import ProbeSignalRepository
from services.routing.service import RoutingService
from services.placements.transport import NodeAgentPlacementTransport
from shared.monitoring.metrics import (
    NODE_STATE_FRESHNESS_SECONDS,
    PLACEMENT_ACTIVE_BY_BACKEND,
    PLACEMENT_AUTO_HEAL_TOTAL,
    PLACEMENT_ORPHAN_ACTIVE_TOTAL,
)
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("node-auto-heal"))


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
    _HEARTBEAT_DETAILS_KEY = "heartbeat"
    _DRAIN_REASON_UNHEALTHY_HEARTBEAT = "unhealthy_heartbeat"
    _PROBE_DRAIN_REASON_PREFIX = "probe_"

    def __init__(
        self,
        session: AsyncSession,
        *,
        stale_after_sec: int,
        max_nodes: int,
        auto_undrain_enabled: bool,
        drain_cooldown_sec: int = 180,
    ):
        self.node_repository = VpnNodeRepository(session)
        self.node_agent_state_repository = NodeAgentStateRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.node_agent_transport = NodeAgentPlacementTransport(session)
        self.probe_repository = ProbeSignalRepository(session)
        self.routing_service = RoutingService(session)
        self.stale_after_sec = max(30, int(stale_after_sec))
        self.max_nodes = min(500, max(1, int(max_nodes)))
        self.auto_undrain_enabled = bool(auto_undrain_enabled)
        self.drain_cooldown_sec = max(0, int(drain_cooldown_sec))
        probe_settings = get_settings().probe
        self.probe_auto_undrain_enabled = bool(probe_settings.auto_undrain_enabled)
        self.probe_auto_undrain_source = probe_settings.auto_undrain_source or probe_settings.auto_drain_source
        self.probe_auto_undrain_max_probe_age_sec = max(30, int(probe_settings.auto_undrain_max_probe_age_sec))
        self.probe_auto_undrain_min_consecutive_successes = max(
            1,
            int(probe_settings.auto_undrain_min_consecutive_successes),
        )

    async def run_once(self) -> NodeAutoHealTickOut:
        now = datetime.now(timezone.utc)
        out = NodeAutoHealTickOut()

        await self._observe_node_freshness(now=now)

        desired_active_counts = await self.placement_repository.count_desired_active_by_backend_node()
        logger.info(
            "auto_heal_desired_active",
            counts={str(k): v for k, v in desired_active_counts.items()},
        )
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
            logger.info(
                "auto_heal_node_eval",
                node_id=str(source_node_id),
                node_name=node.name if node else "N/A",
                reason=reason,
                active_count=active_count,
                freshness=round(self._freshness_seconds(state=state, now=now) or -1, 1),
                stale_threshold=self.stale_after_sec,
            )
            if reason is None:
                continue

            out.processed_nodes += 1
            orphan_total += active_count
            PLACEMENT_AUTO_HEAL_TOTAL.labels(action="evaluate", result=reason).inc()

            if node is not None and not node.is_draining:
                await self.node_repository.update_by_id(node.id, {"is_draining": True})
                await self._record_drain_reason(
                    node_id=node.id,
                    state=state,
                    reason=self._DRAIN_REASON_UNHEALTHY_HEARTBEAT,
                    now=now,
                )
                out.drained_nodes += 1
                PLACEMENT_AUTO_HEAL_TOTAL.labels(action="drain", result="ok").inc()

            migrated = await self._smart_migrate_placements(
                source_node=node,
                source_node_id=source_node_id,
                updated_at=now,
            )
            if migrated <= 0:
                out.skipped_nodes += 1
                PLACEMENT_AUTO_HEAL_TOTAL.labels(action="migrate", result="no_orphans").inc()
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
            if state is None or not state.is_healthy:
                continue
            freshness = self._freshness_seconds(state=state, now=now)
            if freshness is None or freshness > self.stale_after_sec:
                continue
            has_placements = desired_active_counts.get(node.id, 0) > 0
            heartbeat_meta = self._extract_heartbeat_meta(state)
            if has_placements:
                drain_reason = self._extract_drain_reason(heartbeat_meta)
                if drain_reason is None or drain_reason == self._DRAIN_REASON_UNHEALTHY_HEARTBEAT:
                    pass
                elif self._is_probe_drain_reason(drain_reason):
                    recovered = await self._has_recent_probe_recovery(node_id=node.id, now=now)
                    if not recovered:
                        continue
                else:
                    continue
            await self.node_repository.update_by_id(node.id, {"is_draining": False})
            await self._clear_drain_reason(node_id=node.id, state=state)
            undrained += 1
            PLACEMENT_AUTO_HEAL_TOTAL.labels(action="undrain", result="ok").inc()
            logger.info(
                "node_undrained",
                node_id=str(node.id),
                had_placements=has_placements,
            )
        return undrained

    async def _smart_migrate_placements(
        self,
        *,
        source_node: VpnNode | None,
        source_node_id: UUID,
        updated_at: datetime,
    ) -> int:
        """Migrate only orphan placements (users with no other healthy nodes).

        Covered users (who have active placements on other healthy nodes)
        are left untouched — their placements will resync when the node
        recovers.

        Orphan placements are distributed evenly across available target
        nodes where the user doesn't already have a placement.
        """
        placements = await self.placement_repository.list_active(backend_node_id=source_node_id)
        active = [
            p for p in placements
            if p.desired_state == PlacementDesiredState.active.value
        ]
        if not active:
            return 0

        key_ids = list({p.key_id for p in active})
        key_nodes = await self.placement_repository.map_active_backend_nodes_by_key(
            key_ids=key_ids,
        )

        # Get healthy target candidates (sorted by score, least-loaded first)
        preferred_region = source_node.region if source_node is not None else None
        candidates = await self.routing_service.select_nodes(
            preferred_region=preferred_region,
            exclude_node_ids=[source_node_id],
        )
        if not candidates:
            logger.info(
                "smart_migrate_no_targets",
                source_node_id=str(source_node_id),
            )
            return 0

        healthy_node_ids = {c.id for c in candidates}

        # Split: covered (user has other healthy nodes) vs orphan (doesn't)
        orphan_placements = []
        covered_count = 0
        for p in active:
            other_nodes = key_nodes.get(p.key_id, set()) - {source_node_id}
            if other_nodes & healthy_node_ids:
                covered_count += 1
            else:
                orphan_placements.append(p)

        if covered_count > 0:
            logger.info(
                "smart_migrate_covered_skipped",
                source_node_id=str(source_node_id),
                covered=covered_count,
                orphans=len(orphan_placements),
            )

        if not orphan_placements:
            return 0

        # Distribute orphans across targets where key isn't already placed.
        # Track how many we assign to each target for even distribution.
        target_load: dict[UUID, int] = {c.id: 0 for c in candidates}
        groups: dict[UUID, list[UUID]] = defaultdict(list)

        for p in orphan_placements:
            existing_nodes = key_nodes.get(p.key_id, set())
            available = [c for c in candidates if c.id not in existing_nodes]
            if not available:
                available = candidates
            # Pick least-loaded target among available
            best = min(available, key=lambda c: target_load[c.id])
            groups[best.id].append(p.id)
            target_load[best.id] += 1

        total_migrated = 0
        for target_id, placement_ids in groups.items():
            migrated, target_ids = await self.placement_repository.bulk_migrate_backend(
                placement_ids=placement_ids,
                target_backend_id=target_id,
                last_migration_reason="node_auto_heal",
                updated_at=updated_at,
            )
            if target_ids:
                await self.node_agent_transport.enqueue_for_placement_ids(target_ids)
            total_migrated += migrated

        target_name = lambda tid: next((c.name for c in candidates if c.id == tid), str(tid))
        logger.info(
            "smart_migrate_result",
            source_node_id=str(source_node_id),
            total_migrated=total_migrated,
            distribution={target_name(tid): len(pids) for tid, pids in groups.items()},
        )
        return total_migrated

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
            if self._is_within_drain_cooldown(state=state, now=now):
                return None
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

    def _is_within_drain_cooldown(
        self,
        *,
        state: NodeAgentState | None,
        now: datetime,
    ) -> bool:
        if self.drain_cooldown_sec <= 0:
            return False
        heartbeat_meta = self._extract_heartbeat_meta(state)
        if heartbeat_meta is None:
            return False
        if heartbeat_meta.drain_reason != self._DRAIN_REASON_UNHEALTHY_HEARTBEAT:
            return False
        drained_at_raw = heartbeat_meta.drained_at
        if drained_at_raw is None:
            return False
        try:
            drained_at = drained_at_raw
            if drained_at.tzinfo is None:
                drained_at = drained_at.replace(tzinfo=timezone.utc)
            elapsed = (now - drained_at).total_seconds()
            if elapsed < self.drain_cooldown_sec:
                logger.info(
                    "drain_cooldown_active",
                    elapsed_sec=round(elapsed),
                    cooldown_sec=self.drain_cooldown_sec,
                )
                return True
        except (TypeError, ValueError):
            pass
        return False

    async def _has_recent_probe_recovery(
        self,
        *,
        node_id: UUID,
        now: datetime,
    ) -> bool:
        if not self.probe_auto_undrain_enabled:
            return False
        latest = await self.probe_repository.get_latest_for_backend_node(
            node_id=node_id,
            source=self.probe_auto_undrain_source,
        )
        if latest is None or not latest.is_reachable:
            return False
        checked_at = latest.checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        else:
            checked_at = checked_at.astimezone(timezone.utc)
        if now - checked_at > timedelta(seconds=self.probe_auto_undrain_max_probe_age_sec):
            return False
        recent = await self.probe_repository.list_recent_for_backend_node(
            limit=max(10, self.probe_auto_undrain_min_consecutive_successes * 3),
            node_id=node_id,
            source=self.probe_auto_undrain_source,
        )
        consecutive_successes = 0
        for signal in recent:
            if not signal.is_reachable:
                break
            consecutive_successes += 1
        return consecutive_successes >= self.probe_auto_undrain_min_consecutive_successes

    async def _record_drain_reason(
        self,
        *,
        node_id: UUID,
        state: NodeAgentState | None,
        reason: str,
        now: datetime,
    ) -> None:
        heartbeat_meta = self._extract_heartbeat_meta(state)
        if heartbeat_meta is None:
            heartbeat_meta = NodeHeartbeatMeta()
        heartbeat_meta.drain_reason = reason
        heartbeat_meta.drained_at = now
        details = dict(state.details) if state is not None and isinstance(state.details, dict) else {}
        details[self._HEARTBEAT_DETAILS_KEY] = heartbeat_meta.model_dump(mode="json", exclude_none=True)
        if state is not None:
            await self.node_agent_state_repository.update_by_node_id(node_id, {"details": details})
        logger.info(
            "drain_reason_recorded",
            node_id=str(node_id),
            reason=reason,
        )

    async def _clear_drain_reason(
        self,
        *,
        node_id: UUID,
        state: NodeAgentState | None,
    ) -> None:
        heartbeat_meta = self._extract_heartbeat_meta(state)
        if heartbeat_meta is None:
            return
        changed = False
        if heartbeat_meta.drain_reason is not None:
            heartbeat_meta.drain_reason = None
            changed = True
        if heartbeat_meta.drained_at is not None:
            heartbeat_meta.drained_at = None
            changed = True
        if not changed:
            return
        details = dict(state.details) if isinstance(state.details, dict) else {}
        details[self._HEARTBEAT_DETAILS_KEY] = heartbeat_meta.model_dump(mode="json", exclude_none=True)
        await self.node_agent_state_repository.update_by_node_id(node_id, {"details": details})

    @staticmethod
    def _extract_heartbeat_meta(state: NodeAgentState | None) -> NodeHeartbeatMeta | None:
        if state is None:
            return None
        details = state.details if isinstance(state.details, dict) else {}
        heartbeat = details.get("heartbeat")
        heartbeat_data = heartbeat if isinstance(heartbeat, dict) else {}
        return NodeHeartbeatMeta.model_validate(heartbeat_data)

    @staticmethod
    def _extract_drain_reason(heartbeat_meta: NodeHeartbeatMeta | None) -> str | None:
        if heartbeat_meta is None:
            return None
        if isinstance(heartbeat_meta.drain_reason, str):
            normalized = heartbeat_meta.drain_reason.strip()
            return normalized or None
        return None

    @classmethod
    def _is_probe_drain_reason(cls, drain_reason: str | None) -> bool:
        return bool(drain_reason and drain_reason.startswith(cls._PROBE_DRAIN_REASON_PREFIX))

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
