from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RouteHealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    suspected = "suspected"
    blocked = "blocked"
    warming_up = "warming_up"


class RouteHealthAction(str, Enum):
    block = "block"
    recover = "recover"
    set_healthy = "set_healthy"
    set_degraded = "set_degraded"
    set_suspected = "set_suspected"


class TransportProfileCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    protocol: str = Field(default="vless", min_length=1, max_length=16)
    network: str = Field(default="tcp", min_length=1, max_length=16)
    security: str = Field(default="reality", min_length=1, max_length=16)
    flow: str | None = Field(default=None, max_length=64)
    reality_public_key: str | None = Field(default=None, max_length=128)
    reality_short_id: str | None = Field(default=None, max_length=32)
    reality_server_name: str | None = Field(default=None, max_length=255)
    tls_fingerprint: str = Field(default="chrome", min_length=1, max_length=64)
    grpc_service_name: str | None = Field(default=None, max_length=64)
    port: int = Field(default=443, ge=1, le=65535)


class TransportProfileOut(BaseModel):
    id: UUID
    name: str
    protocol: str
    network: str
    security: str
    flow: str | None
    reality_public_key: str | None
    reality_short_id: str | None
    reality_server_name: str | None
    tls_fingerprint: str
    grpc_service_name: str | None
    port: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RouteCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    node_id: UUID
    transport_profile_id: UUID
    base_weight: int = Field(default=50, ge=0, le=100)
    effective_weight: int | None = Field(default=None, ge=0, le=100)
    health_status: RouteHealthStatus = RouteHealthStatus.healthy


class RouteOut(BaseModel):
    id: UUID
    name: str
    node_id: UUID
    transport_profile_id: UUID
    health_status: RouteHealthStatus
    base_weight: int
    effective_weight: int
    cooldown_until: datetime | None
    warmup_stage: int | None
    warmup_started_at: datetime | None
    routing_eligible: bool = False
    routing_reason: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RouteHealthUpdateIn(BaseModel):
    action: RouteHealthAction
    cooldown_hours: int = Field(default=6, ge=1, le=72)


class RouteWarmupTickOut(BaseModel):
    processed: int
    advanced: int
    finalized: int


class ProfileReactivationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    protocol: str = Field(min_length=1, max_length=16)
    network: str = Field(min_length=1, max_length=16)
    security: str = Field(min_length=1, max_length=16)
    flow: str | None = Field(default=None, max_length=64)
    reality_public_key: str | None = Field(default=None, max_length=128)
    reality_short_id: str | None = Field(default=None, max_length=32)
    reality_server_name: str | None = Field(default=None, max_length=255)
    tls_fingerprint: str = Field(min_length=1, max_length=64)
    grpc_service_name: str | None = Field(default=None, max_length=64)
    port: int = Field(ge=1, le=65535)
    is_active: bool = True


class RouteReactivationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    node_id: UUID
    transport_profile_id: UUID
    health_status: RouteHealthStatus
    base_weight: int = Field(ge=0, le=100)
    effective_weight: int = Field(ge=0, le=100)
    cooldown_until: datetime | None = None
    warmup_stage: int | None = None
    warmup_started_at: datetime | None = None
    is_active: bool = True


class RouteCreateData(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    node_id: UUID
    transport_profile_id: UUID
    health_status: RouteHealthStatus
    base_weight: int = Field(ge=0, le=100)
    effective_weight: int = Field(ge=0, le=100)
    cooldown_until: datetime | None = None
    warmup_stage: int | None = None
    warmup_started_at: datetime | None = None
    is_active: bool = True


class RouteStateUpdate(BaseModel):
    health_status: RouteHealthStatus
    effective_weight: int = Field(ge=0, le=100)
    cooldown_until: datetime | None = None
    warmup_stage: int | None = None
    warmup_started_at: datetime | None = None
    updated_at: datetime
