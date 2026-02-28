from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class SubscriptionCreateIn(BaseModel):
    user_id: UUID
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    expires_at: datetime | None = None
    max_devices: int | None = Field(default=None, gt=0, le=100)


class SubscriptionInternalCreate(BaseModel):
    user_id: UUID
    token_hash: str = Field(min_length=64, max_length=64)
    prev_token_hash: str | None = None
    prev_token_expires_at: datetime | None = None
    is_active: bool = True
    expires_at: datetime | None = None
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    hwid_enabled: bool = True
    max_devices: int | None = Field(default=None, gt=0, le=100)


class SubscriptionInternalUpdate(BaseModel):
    is_active: bool | None = None
    expires_at: datetime | None = None
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    hwid_enabled: bool | None = None
    max_devices: int | None = Field(default=None, gt=0, le=100)
    updated_at: datetime | None = None


class SubscriptionCreatedOut(BaseModel):
    id: UUID
    vpn_key_id: UUID | None = None
    token: str
    subscription_url: str
    expires_at: datetime | None
    is_active: bool


class SubscriptionOut(BaseModel):
    id: UUID
    user_id: UUID
    is_active: bool
    expires_at: datetime | None
    profile_key: str | None
    preferred_region: str | None
    hwid_enabled: bool
    max_devices: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionInternalRotate(BaseModel):
    token_hash: str = Field(min_length=64, max_length=64)
    prev_token_hash: str | None
    prev_token_expires_at: datetime | None
    updated_at: datetime


class SubscriptionRotateOut(BaseModel):
    token: str


class SubscriptionStatsOut(BaseModel):
    total_requests: int
    last_accessed_at: datetime | None


class SubscriptionDeviceCreate(BaseModel):
    subscription_id: UUID
    hwid_hash: str
    vpn_key_id: UUID
    last_seen_at: datetime | None
    user_agent: str | None


class SubscriptionDeviceInternalUpdate(BaseModel):
    is_active: bool | None = None
    last_seen_at: datetime | None = None
    user_agent: str | None = None
    updated_at: datetime | None = None


class SubscriptionDeviceOut(BaseModel):
    id: UUID
    subscription_id: UUID
    vpn_key_id: UUID
    hwid_hash: str
    last_seen_at: datetime | None
    user_agent: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResolvedSubscriptionRoute(BaseModel):
    route_id: UUID
    backend_node_id: UUID
    transport_security: str
    transport_network: str
    uri: str
    route: Any
    node: Any
    transport_profile: Any

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class SubscriptionPublicSuccessResponse(BaseModel):
    metric_result: str
    status_code: int
    payload: str | None
    headers: dict[str, str]

    model_config = ConfigDict(frozen=True)


class SubscriptionPublicErrorResponse(BaseModel):
    metric_result: str
    status_code: int
    detail: str

    model_config = ConfigDict(frozen=True)
