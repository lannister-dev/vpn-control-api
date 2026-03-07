from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_status.schemas import (
    AdminNodeStatusOut,
    AdminReadinessCheckOut,
    AdminReadinessOut,
    AdminStatusOut,
    AdminStatusTotalsOut,
)
from services.artifacts.repository import ProfileArtifactRepository
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import NodeRole
from services.placements.repository import UserPlacementRepository
from services.routes.repository import RouteRepository
from shared.database.session import AsyncDatabase


class AdminStatusService:
    def __init__(self, session: AsyncSession):
        self.node_repository = VpnNodeRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.route_repository = RouteRepository(session)
        self.profile_artifact_repository = ProfileArtifactRepository(session)

    async def get_status(self) -> AdminStatusOut:
        node_rows = await self.node_repository.list_active_with_agent_state()
        placements_backend = await self.placement_repository.count_active_by_backend_node()

        nodes: list[AdminNodeStatusOut] = []
        nodes_enabled = 0
        nodes_draining = 0
        nodes_healthy = 0

        for node, agent_state in node_rows:
            healthy = bool(agent_state and agent_state.is_healthy)
            if node.is_enabled:
                nodes_enabled += 1
            if node.is_draining:
                nodes_draining += 1
            if healthy:
                nodes_healthy += 1

            role_raw = node.role
            role = NodeRole(role_raw) if role_raw in (NodeRole.backend.value, NodeRole.gateway.value) else NodeRole.backend
            reality_ip_raw = getattr(node, "reality_ip", None)
            reality_ip = reality_ip_raw if isinstance(reality_ip_raw, str) else None

            nodes.append(
                AdminNodeStatusOut(
                    id=node.id,
                    name=node.name,
                    role=role,
                    region=node.region,
                    public_domain=node.public_domain,
                    reality_ip=reality_ip,
                    is_enabled=node.is_enabled,
                    is_draining=node.is_draining,
                    capacity=node.capacity,
                    is_healthy=healthy,
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
        resolved_routes = await self.route_repository.count_resolved_active()
        resolved_routes_by_region = await self.route_repository.count_resolved_active_by_region()

        healthy_backends = 0
        healthy_regions: set[str] = set()
        for node, agent_state in node_rows:
            if node.role != NodeRole.backend.value:
                continue
            if not node.is_active or not node.is_enabled or node.is_draining:
                continue
            if bool(agent_state and agent_state.is_healthy):
                healthy_backends += 1
                healthy_regions.add(str(node.region))

        route_regions = {str(region) for region in resolved_routes_by_region.keys()}
        missing_regions = sorted(healthy_regions - route_regions)
        region_coverage_ok = bool(healthy_regions) and not missing_regions
        if region_coverage_ok:
            region_detail = f"regions covered: {', '.join(sorted(healthy_regions))}"
        elif not healthy_regions:
            region_detail = "no healthy backend regions"
        else:
            region_detail = f"missing route coverage for regions: {', '.join(missing_regions)}"

        checks = [
            AdminReadinessCheckOut(
                name="active_profiles_artifact",
                ok=active_artifact is not None,
                detail="active artifact found" if active_artifact is not None else "no active artifact",
            ),
            AdminReadinessCheckOut(
                name="healthy_backend_nodes",
                ok=healthy_backends > 0,
                detail=f"healthy backends: {healthy_backends}",
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


def get_admin_status_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> AdminStatusService:
    return AdminStatusService(session)
