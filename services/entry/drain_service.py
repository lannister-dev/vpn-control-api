from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.entry.constants import ENTRY_ROLES
from services.entry.events import enqueue_pool_snapshots_for_backend
from services.entry.repository import EntryBackendAssignmentRepository
from services.nodes.constants import (
    DRAIN_REASON_ENTRY_AUTO_DRAIN,
    HEARTBEAT_DETAILS_KEY,
)
from services.nodes.models import NodeAgentState, VpnNode
from services.nodes.repository import NodeAgentStateRepository, VpnNodeRepository
from services.probe.repository import ProbeSignalRepository
from services.routes.model import Route
from services.routes.repository import RouteRepository
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("entry-auto-drain-service"))


@dataclass(slots=True)
class EntryAutoDrainResult:
    processed: int
    drained: int
    routes_blocked: int
    snapshots_enqueued: int
    skipped: int
    undrained: int = 0
    routes_unblocked: int = 0


class EntryAutoDrainService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        probe_failure_threshold: int,
        drain_reason: str,
        max_nodes: int,
        auto_undrain_enabled: bool = True,
        healthy_ticks_for_recovery: int = 3,
    ):
        self.session = session
        self.node_repository = VpnNodeRepository(session)
        self.agent_state_repository = NodeAgentStateRepository(session)
        self.probe_repository = ProbeSignalRepository(session)
        self.route_repository = RouteRepository(session)
        self.assignment_repository = EntryBackendAssignmentRepository(session)
        self.probe_failure_threshold = probe_failure_threshold
        self.drain_reason = drain_reason
        self.max_nodes = max_nodes
        self.auto_undrain_enabled = auto_undrain_enabled
        self.healthy_ticks_for_recovery = max(1, int(healthy_ticks_for_recovery))

    async def run(self) -> EntryAutoDrainResult:
        candidates = await self._list_entry_candidates()
        result = EntryAutoDrainResult(
            processed=0, drained=0, routes_blocked=0, snapshots_enqueued=0, skipped=0,
        )
        processed = 0
        for entry, agent_state in candidates:
            if processed >= self.max_nodes:
                break
            processed += 1
            result.processed += 1

            reason = await self._unhealthy_reason(entry=entry, agent_state=agent_state)
            if reason is None:
                if self.auto_undrain_enabled and entry.is_draining:
                    undrained = await self._try_undrain_entry(entry=entry, agent_state=agent_state)
                    if undrained:
                        result.undrained += 1
                        result.routes_unblocked += await self._unblock_routes_for_entry(
                            entry_node_id=entry.id,
                        )
                        result.snapshots_enqueued += await self._notify_alternative_entries(entry=entry)
                        continue
                result.skipped += 1
                continue

            drained = await self._drain_entry(entry=entry, reason=reason, agent_state=agent_state)
            result.drained += int(drained)
            blocked = await self._block_routes_for_entry(entry_node_id=entry.id)
            result.routes_blocked += blocked
            snapshots = await self._notify_alternative_entries(entry=entry)
            result.snapshots_enqueued += snapshots

        return result

    async def _list_entry_candidates(self) -> list[tuple[VpnNode, NodeAgentState | None]]:
        stmt = (
            select(VpnNode, NodeAgentState)
            .outerjoin(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .where(VpnNode.is_active.is_(True))
            .where(VpnNode.is_enabled.is_(True))
            .where(VpnNode.role.in_(tuple(ENTRY_ROLES)))
            .order_by(VpnNode.name.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.tuples().all())

    async def _unhealthy_reason(
        self,
        *,
        entry: VpnNode,
        agent_state: NodeAgentState | None,
    ) -> str | None:
        if agent_state is not None and not agent_state.is_healthy:
            return "agent_unhealthy"
        if self.probe_failure_threshold > 0:
            consecutive = await self.probe_repository.count_consecutive_node_failures(
                node_id=entry.id,
                limit=max(self.probe_failure_threshold * 3, 10),
            )
            if consecutive >= self.probe_failure_threshold:
                return f"probe_failures:{consecutive}"
        return None

    async def _drain_entry(
        self,
        *,
        entry: VpnNode,
        reason: str,
        agent_state: NodeAgentState | None,
    ) -> bool:
        if entry.is_draining:
            return False
        await self.node_repository.update_by_id(entry.id, {"is_draining": True})
        entry.is_draining = True
        await self._mark_drain_meta(
            agent_state=agent_state,
            drain_reason=DRAIN_REASON_ENTRY_AUTO_DRAIN,
            drained_at=datetime.now(timezone.utc),
        )
        logger.warning(
            "entry_auto_drain_triggered",
            entry_id=str(entry.id),
            entry_name=entry.name,
            reason=reason,
        )
        return True

    async def _try_undrain_entry(
        self,
        *,
        entry: VpnNode,
        agent_state: NodeAgentState | None,
    ) -> bool:
        if agent_state is None:
            return False
        meta = self._read_heartbeat_meta(agent_state)
        if meta.get("drain_reason") != DRAIN_REASON_ENTRY_AUTO_DRAIN:
            return False
        consecutive_healthy = int(meta.get("consecutive_healthy") or 0)
        if consecutive_healthy < self.healthy_ticks_for_recovery:
            return False
        await self.node_repository.update_by_id(entry.id, {"is_draining": False})
        entry.is_draining = False
        await self._mark_drain_meta(
            agent_state=agent_state,
            drain_reason=None,
            drained_at=None,
        )
        logger.info(
            "entry_auto_undrain",
            entry_id=str(entry.id),
            entry_name=entry.name,
            healthy_ticks=consecutive_healthy,
        )
        return True

    @staticmethod
    def _read_heartbeat_meta(agent_state: NodeAgentState) -> dict:
        details = agent_state.details or {}
        if not isinstance(details, dict):
            return {}
        raw = details.get(HEARTBEAT_DETAILS_KEY)
        return raw if isinstance(raw, dict) else {}

    async def _mark_drain_meta(
        self,
        *,
        agent_state: NodeAgentState | None,
        drain_reason: str | None,
        drained_at,
    ) -> None:
        if agent_state is None:
            return
        details = agent_state.details or {}
        if not isinstance(details, dict):
            details = {}
        meta = dict(details.get(HEARTBEAT_DETAILS_KEY) or {})
        if drain_reason is None:
            meta.pop("drain_reason", None)
            meta.pop("drained_at", None)
        else:
            meta["drain_reason"] = drain_reason
            if drained_at is not None:
                meta["drained_at"] = drained_at.isoformat()
        new_details = {**details, HEARTBEAT_DETAILS_KEY: meta}
        await self.agent_state_repository.update_by_id(
            agent_state.id,
            {"details": new_details},
        )
        agent_state.details = new_details

    async def _unblock_routes_for_entry(self, *, entry_node_id: UUID) -> int:
        stmt = select(Route).where(
            Route.entry_node_id == entry_node_id,
            Route.is_active.is_(True),
            Route.health_status == "blocked",
        )
        res = await self.session.execute(stmt)
        routes = list(res.scalars().all())
        if not routes:
            return 0
        for route in routes:
            base_weight = int(getattr(route, "base_weight", 0) or 0)
            await self.route_repository.update_by_id(
                route.id,
                {
                    "health_status": "warming_up",
                    "effective_weight": max(1, base_weight // 2),
                    "warmup_stage": 1,
                    "warmup_started_at": datetime.now(timezone.utc),
                },
            )
        return len(routes)

    async def _block_routes_for_entry(self, *, entry_node_id: UUID) -> int:
        stmt = select(Route).where(
            Route.entry_node_id == entry_node_id,
            Route.is_active.is_(True),
            Route.health_status != "blocked",
        )
        res = await self.session.execute(stmt)
        routes = list(res.scalars().all())
        if not routes:
            return 0
        for route in routes:
            await self.route_repository.update_by_id(
                route.id,
                {
                    "health_status": "blocked",
                    "effective_weight": 0,
                },
            )
        return len(routes)

    async def _notify_alternative_entries(self, *, entry: VpnNode) -> int:
        assignments = await self.assignment_repository.list_by_entry(entry.id)
        backend_ids = {a.backend_node_id for a in assignments}
        if not backend_ids:
            return 0
        snapshots = 0
        for backend_id in backend_ids:
            try:
                count = await enqueue_pool_snapshots_for_backend(self.session, backend_id)
                snapshots += int(count or 0)
            except Exception:
                logger.exception(
                    "entry_auto_drain_pool_snapshot_failed",
                    entry_id=str(entry.id),
                    backend_id=str(backend_id),
                )
        return snapshots
