from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConnectIn(BaseModel):
    user_id: UUID
    key_id: UUID | None = None
    profile_key: str = Field(default="ws_tls_v1", min_length=3, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    gateway_node_id: UUID | None = None
    valid_until: datetime | None = None
    traffic_limit_mb: int = Field(default=1000, gt=0)


class ConnectOut(BaseModel):
    key_id: UUID
    client_id: str
    gateway_node_id: UUID
    backend_node_id: UUID
    placement_id: UUID
    placement_op_version: int
    uri: str
