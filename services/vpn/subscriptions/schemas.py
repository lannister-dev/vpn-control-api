from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionCreateIn(BaseModel):
    user_id: UUID
    plan_id: UUID | None = None
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    expires_at: datetime | None = None
    max_devices: int | None = Field(default=None, gt=0, le=100)


class SubscriptionInternalCreate(BaseModel):
    user_id: UUID
    plan_id: UUID | None = None
    token: str = Field(min_length=1, max_length=64)
    token_hash: str = Field(min_length=64, max_length=64)
    prev_token_hash: str | None = None
    prev_token_expires_at: datetime | None = None
    is_active: bool = True
    expires_at: datetime | None = None
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    hwid_enabled: bool = True
    max_devices: int | None = Field(default=None, gt=0, le=100)
    paid_device_slots: int = 0


class SubscriptionInternalUpdate(BaseModel):
    plan_id: UUID | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None
    profile_key: str | None = Field(default=None, max_length=64)
    preferred_region: str | None = Field(default=None, max_length=16)
    hwid_enabled: bool | None = None
    max_devices: int | None = Field(default=None, gt=0, le=100)
    paid_device_slots: int | None = None
    updated_at: datetime | None = None


class SubscriptionSetMaxDevicesIn(BaseModel):
    max_devices: int = Field(gt=0, le=100)


class SubscriptionCountersOut(BaseModel):
    total: int
    active: int
    expired: int
    total_24h_ago: int = 0
    active_24h_ago: int = 0
    expired_24h_ago: int = 0


class SubscriptionListOut(BaseModel):
    items: list["SubscriptionOut"]
    total: int
    limit: int
    offset: int


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
    plan_id: UUID | None = None
    plan_name: str | None = None
    token: str | None = None
    is_active: bool
    expires_at: datetime | None
    profile_key: str | None
    preferred_region: str | None
    hwid_enabled: bool
    max_devices: int | None
    paid_device_slots: int = 0
    used_traffic_bytes: int = 0
    lifetime_used_traffic_bytes: int = 0
    last_traffic_reset_at: datetime | None = None
    device_count: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionInternalRotate(BaseModel):
    token: str = Field(min_length=1, max_length=64)
    token_hash: str = Field(min_length=64, max_length=64)
    prev_token_hash: str | None
    prev_token_expires_at: datetime | None
    updated_at: datetime


class SubscriptionRotateOut(BaseModel):
    token: str
    subscription_url: str


class SubscriptionStatsOut(BaseModel):
    total_requests: int
    last_accessed_at: datetime | None


class SubscriptionDeviceCreate(BaseModel):
    subscription_id: UUID
    hwid_hash: str
    last_seen_at: datetime | None
    user_agent: str | None
    device_model: str | None = None
    platform: str | None = None
    os_version: str | None = None


class SubscriptionDeviceKeyCreate(BaseModel):
    subscription_device_id: UUID
    vpn_key_id: UUID
    transport: str = Field(min_length=1, max_length=16)
    is_primary: bool = False


class SubscriptionDeviceInternalUpdate(BaseModel):
    is_active: bool | None = None
    last_seen_at: datetime | None = None
    user_agent: str | None = None
    device_model: str | None = None
    platform: str | None = None
    os_version: str | None = None
    updated_at: datetime | None = None


class DeviceClientHeaders(BaseModel):
    hwid: str = Field(min_length=1, max_length=128)
    user_agent: str | None = Field(default=None, max_length=255)
    device_model: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default=None, max_length=32)
    os_version: str | None = Field(default=None, max_length=32)


class SubscriptionDeviceKeyOut(BaseModel):
    id: UUID
    subscription_device_id: UUID
    vpn_key_id: UUID
    transport: str
    is_primary: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionNodeRef(BaseModel):
    node_id: UUID
    name: str
    region: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class SubscriptionEntryRouteOut(BaseModel):
    entry: SubscriptionNodeRef
    transport_kind: str | None = None
    health: str
    weight: int


class SubscriptionActiveNodeOut(BaseModel):
    backend: SubscriptionNodeRef
    transport: str | None = None
    device_id: UUID | None = None
    placement_state: str | None = None
    sticky_until: datetime | None = None
    entries: list[SubscriptionEntryRouteOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SubscriptionRouteAssignmentOut(BaseModel):
    device_id: UUID
    transport: str
    last_assigned_at: datetime
    assignment_count: int
    entry: SubscriptionNodeRef
    backend: SubscriptionNodeRef


class EntryDistributionRowOut(BaseModel):
    entry_node_id: UUID
    entry_name: str
    entry_region: str
    entry_role: str
    capacity: int = 0
    subscription_count: int
    device_count: int
    share_pct: float = 0.0
    load_pct: float | None = None
    most_recent_at: datetime | None = None


class NodeAssignmentSlotOut(BaseModel):
    subscription_count: int = 0
    device_count: int = 0
    most_recent_at: datetime | None = None


class NodeAssignmentDistributionOut(BaseModel):
    node_id: UUID
    name: str
    region: str
    role: str
    capacity: int = 0
    as_entry: NodeAssignmentSlotOut | None = None
    as_backend: NodeAssignmentSlotOut | None = None
    total_device_count: int = 0
    load_pct: float | None = None


class SubscriptionDeviceOut(BaseModel):
    id: UUID
    subscription_id: UUID
    vpn_key_ids: list[UUID] = Field(default_factory=list)
    transport_keys: list[SubscriptionDeviceKeyOut] = Field(default_factory=list)
    hwid_hash: str
    last_seen_at: datetime | None
    user_agent: str | None
    device_model: str | None = None
    platform: str | None = None
    os_version: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResolvedDeviceKey(BaseModel):
    vpn_key_id: UUID
    transport: str
    client_id: str
    is_primary: bool
    key: Any

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class ResolvedDeviceBundle(BaseModel):
    device: Any
    keys: tuple[ResolvedDeviceKey, ...]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class ResolvedSubscriptionRoute(BaseModel):
    route_id: UUID
    backend_node_id: UUID
    entry_node_id: UUID | None = None
    vpn_key_id: UUID | None = None
    vpn_transport: str = ""
    client_id: str = ""
    transport_security: str
    transport_network: str
    country_code: str | None = None
    country_name: str | None = None
    display_name: str | None = None
    is_entry_route: bool = False
    is_whitelist_route: bool = False
    preferred_backend: bool = False
    selection_rank: int = 0
    effective_weight: int = 0
    selection_score: float = 0.0
    uri: str
    route: Any
    node: Any
    transport_profile: Any

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class TransportBuildResult(BaseModel):
    key: ResolvedDeviceKey
    routes: tuple[ResolvedSubscriptionRoute, ...]
    placement_signature: str | None
    diagnostic_reason: str | None

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class SubscriptionUserInfo(BaseModel):
    upload: int = 0
    download: int = 0
    total: int = 0
    expire: int = 0

    model_config = ConfigDict(frozen=True)

    def to_header(self) -> str:
        return f"upload={self.upload}; download={self.download}; total={self.total}; expire={self.expire}"


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
