from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class SubscriptionCreateIn(BaseModel):
    user_id: UUID
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    expires_at: datetime | None = None


class SubscriptionInternalCreate(BaseModel):
    user_id: UUID
    client_id: UUID
    token_hash: str = Field(min_length=64, max_length=64)
    prev_token_hash: str | None = None
    prev_token_expires_at: datetime | None = None
    is_active: bool = True
    expires_at: datetime | None = None
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)


class SubscriptionInternalUpdate(BaseModel):
    is_active: bool | None = None
    expires_at: datetime | None = None
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    updated_at: datetime | None = None


class SubscriptionCreatedOut(BaseModel):
    id: UUID
    client_id: UUID
    token: str
    expires_at: datetime | None
    is_active: bool


class SubscriptionOut(BaseModel):
    id: UUID
    user_id: UUID
    client_id: UUID
    is_active: bool
    expires_at: datetime | None
    profile_key: str | None
    preferred_region: str | None
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
