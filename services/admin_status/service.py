from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin_status.schemas import AdminNodeStatusOut, AdminStatusOut, AdminStatusTotalsOut
from services.backend_peers.repository import BackendPeerRepository
from services.nodes.repository import VpnNodeRepository
from services.nodes.schemas import NodeRole
from services.placements.repository import UserPlacementRepository
from shared.database.session import AsyncDatabase


class AdminStatusService:
    def __init__(self, session: AsyncSession):
        self.node_repository = VpnNodeRepository(session)
        self.placement_repository = UserPlacementRepository(session)
        self.backend_peer_repository = BackendPeerRepository(session)

    async def get_status(self) -> AdminStatusOut:
        node_rows = await self.node_repository.list_active_with_agent_state()
        placements_backend = await self.placement_repository.count_active_by_backend_node()
        placements_gateway = await self.placement_repository.count_active_by_gateway_node()
        peers_backend = await self.backend_peer_repository.count_active_by_backend_node()
        peers_gateway = await self.backend_peer_repository.count_active_by_gateway_node()

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

            role_raw = getattr(node, "role", NodeRole.backend.value)
            role = NodeRole(role_raw) if role_raw in (NodeRole.backend.value, NodeRole.gateway.value) else NodeRole.backend

            nodes.append(
                AdminNodeStatusOut(
                    id=node.id,
                    name=node.name,
                    role=role,
                    region=node.region,
                    public_domain=node.public_domain,
                    is_enabled=node.is_enabled,
                    is_draining=node.is_draining,
                    capacity=node.capacity,
                    is_healthy=healthy,
                    last_seen_at=agent_state.last_seen_at if agent_state else None,
                    last_sync_at=agent_state.last_sync_at if agent_state else None,
                    placements_backend=placements_backend.get(node.id, 0),
                    placements_gateway=placements_gateway.get(node.id, 0),
                    backend_peers_backend=peers_backend.get(node.id, 0),
                    backend_peers_gateway=peers_gateway.get(node.id, 0),
                )
            )

        totals = AdminStatusTotalsOut(
            nodes_total=len(node_rows),
            nodes_enabled=nodes_enabled,
            nodes_draining=nodes_draining,
            nodes_healthy=nodes_healthy,
            placements_total=sum(placements_backend.values()),
            backend_peers_total=sum(peers_backend.values()),
        )
        return AdminStatusOut(
            generated_at=datetime.now(timezone.utc),
            totals=totals,
            nodes=nodes,
        )


def get_admin_status_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> AdminStatusService:
    return AdminStatusService(session)
