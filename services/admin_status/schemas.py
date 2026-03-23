from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AdminNodeStatusOut(BaseModel):
    id: UUID
    name: str
    role: str
    region: str
    public_domain: str
    reality_ip: str | None = None
    is_enabled: bool
    is_draining: bool
    capacity: int
    is_healthy: bool
    routing_eligible: bool = False
    routing_reason: str | None = None
    last_seen_at: datetime | None
    last_sync_at: datetime | None
    placements_backend: int


class AdminStatusTotalsOut(BaseModel):
    nodes_total: int
    nodes_enabled: int
    nodes_draining: int
    nodes_healthy: int
    placements_total: int


class AdminStatusOut(BaseModel):
    generated_at: datetime
    totals: AdminStatusTotalsOut
    nodes: list[AdminNodeStatusOut]


class AdminReadinessCheckOut(BaseModel):
    name: str
    ok: bool
    detail: str


class AdminReadinessOut(BaseModel):
    generated_at: datetime
    ready: bool
    checks: list[AdminReadinessCheckOut]


class RuntimeReadinessCheckOut(BaseModel):
    name: str
    ok: bool
    detail: str


class RuntimeReadinessOut(BaseModel):
    generated_at: datetime
    ready: bool
    checks: list[RuntimeReadinessCheckOut]
