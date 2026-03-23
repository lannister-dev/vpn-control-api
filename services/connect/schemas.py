from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConnectRouteSetIn(BaseModel):
    user_id: UUID
    key_id: UUID | None = None
    preferred_region: str | None = Field(default=None, max_length=16)
    valid_until: datetime | None = None
    traffic_limit_mb: int = Field(default=1000, gt=0)
    max_routes: int = Field(default=4, ge=1, le=10)


class ConnectRouteOut(BaseModel):
    route_id: UUID
    route_name: str
    backend_node_id: UUID
    entry_node_id: UUID | None = None
    transport_profile_id: UUID
    health_status: str
    effective_weight: int
    uri: str


class ConnectRouteSetOut(BaseModel):
    key_id: UUID
    client_id: str
    placement_id: UUID
    placement_op_version: int
    config_version: int
    selection_strategy: str
    refresh_interval_sec: int
    max_cache_age_sec: int
    backoff_steps_sec: list[int]
    routes: list[ConnectRouteOut]


class ConnectRefreshPolicy(BaseModel):
    refresh_interval_sec: int
    max_cache_age_sec: int
    backoff_steps_sec: list[int]


class ResolvedRouteInternal(BaseModel):
    route: ConnectRouteOut
    transport_security: str
    transport_network: str

    model_config = ConfigDict(frozen=True)


class ConnectTelemetryEvent(str, Enum):
    connect_success = "connect_success"
    connect_failure = "connect_failure"


class ConnectTelemetryStatus(str, Enum):
    accepted = "accepted"
    skipped = "skipped"


class ConnectTelemetryIn(BaseModel):
    route_id: UUID
    key_id: UUID
    event: ConnectTelemetryEvent
    error: str | None = Field(default=None, max_length=256)


class ConnectTelemetryOut(BaseModel):
    status: ConnectTelemetryStatus
    route_id: UUID
    applied_action: str | None = None
    failure_streak: int | None = None
