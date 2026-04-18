from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EntryBackendAssignIn(BaseModel):
    backend_node_id: UUID
    weight: int = Field(default=100, ge=1, le=100_000)
    enabled: bool = True
    rank: int = Field(default=0, ge=0, le=15)

    model_config = ConfigDict(extra="forbid")


class EntryBackendUpdateIn(BaseModel):
    weight: int | None = Field(default=None, ge=1, le=100_000)
    enabled: bool | None = None
    rank: int | None = Field(default=None, ge=0, le=15)

    model_config = ConfigDict(extra="forbid")


class EntryBackendAssignmentCreate(BaseModel):
    entry_node_id: UUID
    backend_node_id: UUID
    weight: int = Field(default=100, ge=1, le=100_000)
    enabled: bool = True
    rank: int = Field(default=0, ge=0, le=15)


class EntryBackendAssignmentUpdate(BaseModel):
    weight: int | None = Field(default=None, ge=1, le=100_000)
    enabled: bool | None = None
    rank: int | None = Field(default=None, ge=0, le=15)
    is_active: bool | None = None


class EntryBackendAssignmentOut(BaseModel):
    id: UUID
    entry_node_id: UUID
    backend_node_id: UUID
    weight: int
    enabled: bool
    rank: int

    model_config = ConfigDict(from_attributes=True)


class RelayBackendOut(BaseModel):
    id: UUID
    address: str
    port: int
    weight: int
    enabled: bool
    rank: int


class RelayPoolOut(BaseModel):
    entry_id: UUID
    generation: int
    ttl_seconds: int
    backends: list[RelayBackendOut]


class EntryPoolChangedPayload(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    event_id: str
    node_id: str
    emitted_at: datetime
    pool: RelayPoolOut
