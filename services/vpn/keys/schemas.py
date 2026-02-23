from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------- VpnKey ---------------------
class VpnProtocol(str, Enum):
    vless = "vless"


class VpnTransport(str, Enum):
    ws = "ws"
    xhttp = "xhttp"
    tcp = "tcp"


class VpnKeyCreate(BaseModel):
    user_id: UUID
    protocol: VpnProtocol
    transport: VpnTransport
    valid_until: datetime
    traffic_limit_mb: int = Field(gt=0)


class VpnKeyOut(BaseModel):
    id: UUID
    protocol: VpnProtocol
    transport: VpnTransport
    client_id: str
    valid_until: datetime
    traffic_limit_mb: int
    is_revoked: bool

    model_config = ConfigDict(from_attributes=True)


class VpnKeyInternalCreate(BaseModel):
    user_id: UUID
    protocol: VpnProtocol
    transport: VpnTransport
    client_id: str
    valid_until: datetime
    traffic_limit_mb: int
    is_revoked: bool = False

    @field_validator("valid_until")
    @classmethod
    def normalize(cls, v: datetime) -> datetime:
        if v.tzinfo is not None:
            return v.astimezone(timezone.utc)
        return v.replace(tzinfo=timezone.utc)


class VpnKeyInternal(BaseModel):
    protocol: VpnProtocol
    transport: VpnTransport
    client_id: str
    valid_until: datetime | None
    traffic_limit_mb: int | None
    is_revoked: bool

    model_config = ConfigDict(from_attributes=True)
