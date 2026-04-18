from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TrafficPeriod(str, Enum):
    HOUR = "1h"
    DAY = "24h"
    WEEK = "7d"
    MONTH = "30d"


class NodeTrafficIn(BaseModel):
    entry_node_id: UUID | None = None
    backend_node_id: UUID | None = None
    bytes_in: int = Field(ge=0)
    bytes_out: int = Field(ge=0)
    active_sessions: int = Field(default=0, ge=0)
    total_sessions: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="ignore")


class NodeTrafficCreate(BaseModel):
    entry_node_id: UUID | None = None
    backend_node_id: UUID | None = None
    bytes_in: int = Field(ge=0)
    bytes_out: int = Field(ge=0)
    active_sessions: int = Field(default=0, ge=0)
    total_sessions: int = Field(default=0, ge=0)


class NodeTrafficAggregate(BaseModel):
    node_id: UUID
    bytes_in: int
    bytes_out: int
    total_sessions: int
    active_sessions: int


class NodePairAggregate(BaseModel):
    entry_node_id: UUID
    backend_node_id: UUID | None
    bytes_in: int
    bytes_out: int
    total_sessions: int


class NodeTimeseriesBucket(BaseModel):
    ts: datetime
    bytes_in: int
    bytes_out: int
    active_sessions: int


class NodeTrafficSummaryOut(BaseModel):
    node_id: UUID
    role: str
    name: str
    region: str
    is_enabled: bool
    is_draining: bool
    bytes_in: int
    bytes_out: int
    total_bytes: int
    total_sessions: int
    active_sessions: int


class NodeTrafficSummaryListOut(BaseModel):
    period: TrafficPeriod
    from_ts: datetime
    to_ts: datetime
    items: list[NodeTrafficSummaryOut]


class NodeTimeseriesOut(BaseModel):
    node_id: UUID
    period: TrafficPeriod
    from_ts: datetime
    to_ts: datetime
    resolution_seconds: int
    points: list[NodeTimeseriesBucket]


class NodePairTrafficOut(BaseModel):
    entry_node_id: UUID
    entry_name: str
    backend_node_id: UUID | None = None
    backend_name: str | None = None
    bytes_in: int
    bytes_out: int
    total_bytes: int
    total_sessions: int


class NodePairListOut(BaseModel):
    period: TrafficPeriod
    from_ts: datetime
    to_ts: datetime
    items: list[NodePairTrafficOut]
