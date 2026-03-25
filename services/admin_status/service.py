from datetime import datetime, timedelta, timezone

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.config import get_settings
from services.admin_status.schemas import (
    AdminNodeStatusOut,
    AdminReadinessCheckOut,
    AdminReadinessOut,
    AdminStatusOut,
    AdminStatusTotalsOut,
)
from services.artifacts.repository import ProfileArtifactRepository
from services.nodes.repository import VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.routes.repository import RouteRepository
from shared.database.session import AsyncDatabase


class AdminStatusService:
    BACKEND_NODE_ROLE = "backend"

    def __init__(self, session: AsyncSession):
        self.settings = get_settings()
        self.node_state_stale_after_sec = max(30, int(self.settings.node_agent.stale_after_sec))
        self.node_repository = VpnNodeRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.route_repository = RouteRepository(session)
        self.profile_artifact_repository = ProfileArtifactRepository(session)

    async def get_status(self) -> AdminStatusOut:
        node_rows = await self.node_repository.list_active_with_agent_state()
        placements_backend = await self.placement_repository.count_active_by_backend_node()
        now = datetime.now(timezone.utc)

        nodes: list[AdminNodeStatusOut] = []
        nodes_enabled = 0
        nodes_draining = 0
        nodes_healthy = 0

        for node, agent_state in node_rows:
            healthy = self._is_recent_healthy(agent_state, now=now)
            routing_reason = self._routing_reason(node=node, agent_state=agent_state, now=now)
            routing_eligible = routing_reason is None
            if node.is_enabled:
                nodes_enabled += 1
            if node.is_draining:
                nodes_draining += 1
            if healthy:
                nodes_healthy += 1

            reality_ip_raw = getattr(node, "reality_ip", None)
            reality_ip = reality_ip_raw if isinstance(reality_ip_raw, str) else None

            upstream_raw = getattr(node, "upstream_node_id", None)
            upstream_node_id = upstream_raw if upstream_raw is not None else None

            nodes.append(
                AdminNodeStatusOut(
                    id=node.id,
                    name=node.name,
                    role=self._normalized_node_role(node, default=self.BACKEND_NODE_ROLE),
                    region=node.region,
                    public_domain=node.public_domain,
                    reality_ip=reality_ip,
                    upstream_node_id=upstream_node_id,
                    is_enabled=node.is_enabled,
                    is_draining=node.is_draining,
                    capacity=node.capacity,
                    is_healthy=healthy,
                    routing_eligible=routing_eligible,
                    routing_reason=routing_reason,
                    last_seen_at=agent_state.last_seen_at if agent_state else None,
                    last_sync_at=agent_state.last_sync_at if agent_state else None,
                    placements_backend=placements_backend.get(node.id, 0),
                )
            )

        totals = AdminStatusTotalsOut(
            nodes_total=len(node_rows),
            nodes_enabled=nodes_enabled,
            nodes_draining=nodes_draining,
            nodes_healthy=nodes_healthy,
            placements_total=sum(placements_backend.values()),
        )
        return AdminStatusOut(
            generated_at=datetime.now(timezone.utc),
            totals=totals,
            nodes=nodes,
        )

    async def get_readiness(self) -> AdminReadinessOut:
        node_rows = await self.node_repository.list_active_with_agent_state()
        active_artifact = await self.profile_artifact_repository.get_active()
        node_seen_after = self._node_seen_after(now=datetime.now(timezone.utc))
        resolved_routes = await self.route_repository.count_resolved_active(
            node_seen_after=node_seen_after,
        )
        resolved_routes_by_region = await self.route_repository.count_resolved_active_by_region(
            node_seen_after=node_seen_after,
        )

        healthy_nodes = 0
        healthy_regions: set[str] = set()
        now = datetime.now(timezone.utc)
        for node, agent_state in node_rows:
            if self._normalized_node_role(node, default=self.BACKEND_NODE_ROLE) != self.BACKEND_NODE_ROLE:
                continue
            if not node.is_active or not node.is_enabled or node.is_draining:
                continue
            if self._is_recent_healthy(agent_state, now=now):
                healthy_nodes += 1
                healthy_regions.add(str(node.region))

        route_regions = {str(region) for region in resolved_routes_by_region.keys()}
        missing_regions = sorted(healthy_regions - route_regions)
        region_coverage_ok = bool(healthy_regions) and not missing_regions
        if region_coverage_ok:
            region_detail = f"regions covered: {', '.join(sorted(healthy_regions))}"
        elif not healthy_regions:
            region_detail = "no healthy node regions"
        else:
            region_detail = f"missing route coverage for regions: {', '.join(missing_regions)}"

        checks = [
            AdminReadinessCheckOut(
                name="active_profiles_artifact",
                ok=active_artifact is not None,
                detail="active artifact found" if active_artifact is not None else "no active artifact",
            ),
            AdminReadinessCheckOut(
                name="healthy_nodes",
                ok=healthy_nodes > 0,
                detail=f"healthy nodes: {healthy_nodes}",
            ),
            AdminReadinessCheckOut(
                name="resolvable_active_routes",
                ok=resolved_routes > 0,
                detail=f"resolved active routes: {resolved_routes}",
            ),
            AdminReadinessCheckOut(
                name="healthy_regions_route_coverage",
                ok=region_coverage_ok,
                detail=region_detail,
            ),
        ]
        return AdminReadinessOut(
            generated_at=datetime.now(timezone.utc),
            ready=all(item.ok for item in checks),
            checks=checks,
        )

    def _node_seen_after(self, *, now: datetime) -> datetime:
        return now - timedelta(seconds=self.node_state_stale_after_sec)

    def _is_recent_healthy(self, agent_state, *, now: datetime) -> bool:
        if agent_state is None or not bool(agent_state.is_healthy):
            return False
        last_seen_at = self._to_utc_or_none(agent_state.last_seen_at)
        if last_seen_at is None:
            return False
        return last_seen_at >= self._node_seen_after(now=now)

    def _routing_reason(self, *, node, agent_state, now: datetime) -> str | None:
        if self._normalized_node_role(node, default=self.BACKEND_NODE_ROLE) != self.BACKEND_NODE_ROLE:
            return "node_role_excluded"
        if not node.is_active:
            return "node_inactive"
        if not node.is_enabled:
            return "node_disabled"
        if node.is_draining:
            return "node_draining"
        if agent_state is None:
            return "agent_state_missing"
        if not bool(agent_state.is_healthy):
            return "agent_unhealthy"
        last_seen_at = self._to_utc_or_none(agent_state.last_seen_at)
        if last_seen_at is None:
            return "heartbeat_missing"
        if last_seen_at < self._node_seen_after(now=now):
            return "heartbeat_stale"
        return None

    @staticmethod
    def _to_utc_or_none(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _normalized_node_role(node, *, default: str) -> str:
        raw = getattr(node, "role", default)
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized:
                return normalized
        return default


def get_admin_status_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> AdminStatusService:
    return AdminStatusService(session)
