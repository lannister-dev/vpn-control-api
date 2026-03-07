from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserTrafficIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=128)
    uplink_bytes: int = Field(default=0, ge=0)
    downlink_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="ignore")


class TrafficUsageCreate(BaseModel):
    key_id: UUID
    delta_bytes: int = Field(ge=0)
    reported_total_bytes: int = Field(ge=0)
