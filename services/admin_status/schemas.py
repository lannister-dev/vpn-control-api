from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from services.nodes.schemas import NodeRole


class AdminNodeStatusOut(BaseModel):
    id: UUID
    name: str
    role: NodeRole
    region: str
    public_domain: str
    is_enabled: bool
    is_draining: bool
    capacity: int
    is_healthy: bool
    last_seen_at: datetime | None
    last_sync_at: datetime | None
    placements_backend: int
    placements_gateway: int
    backend_peers_backend: int
    backend_peers_gateway: int


class AdminStatusTotalsOut(BaseModel):
    nodes_total: int
    nodes_enabled: int
    nodes_draining: int
    nodes_healthy: int
    placements_total: int
    backend_peers_total: int


class AdminStatusOut(BaseModel):
    generated_at: datetime
    totals: AdminStatusTotalsOut
    nodes: list[AdminNodeStatusOut]
