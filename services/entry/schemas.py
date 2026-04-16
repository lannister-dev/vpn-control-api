from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EntryBackendAssignIn(BaseModel):
    backend_node_id: UUID
    weight: int = Field(default=100, ge=1, le=100_000)
    enabled: bool = True

    model_config = ConfigDict(extra="forbid")


class EntryBackendUpdateIn(BaseModel):
    weight: int | None = Field(default=None, ge=1, le=100_000)
    enabled: bool | None = None

    model_config = ConfigDict(extra="forbid")


class EntryBackendAssignmentOut(BaseModel):
    id: UUID
    entry_node_id: UUID
    backend_node_id: UUID
    weight: int
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class RelayBackendOut(BaseModel):
    id: UUID
    address: str
    port: int
    weight: int
    enabled: bool


class RelayPoolOut(BaseModel):
    entry_id: UUID
    generation: int
    ttl_seconds: int
    backends: list[RelayBackendOut]
