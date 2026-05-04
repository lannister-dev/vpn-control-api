from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WgPubkeyKvPayload(BaseModel):
    node_id: UUID
    public_key: str = Field(min_length=43, max_length=64)
    listen_port: int = Field(default=51820, ge=1, le=65535)
    auth_token: str = Field(min_length=8)

    model_config = ConfigDict(extra="forbid")


class WgPeerOut(BaseModel):
    node_id: UUID
    name: str
    public_key: str
    endpoint: str
    listen_port: int
    address: str

    model_config = ConfigDict(extra="forbid")


