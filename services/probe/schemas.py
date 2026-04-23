from datetime import datetime
import json
from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ProbeDetailsValue: TypeAlias = str | int | float | bool | None
ProbeDetails: TypeAlias = dict[str, ProbeDetailsValue]
ProbeTransportKind: TypeAlias = Literal["reality", "ws"]
ProbeKind: TypeAlias = Literal["tcp_connect", "synthetic_vpn"]
ProbeTargetRole: TypeAlias = Literal["backend", "whitelist_entry", "entry", "all"]
ProbeErrorPhase: TypeAlias = Literal[
    "dns",
    "tcp",
    "tls",
    "reality_handshake",
    "ws_upgrade",
    "tunnel_http",
]


class ProbeReportIn(BaseModel):
    node_id: UUID
    route_id: UUID | None = None
    transport_profile_id: UUID | None = None
    transport_kind: ProbeTransportKind | None = None
    probe_kind: ProbeKind = "tcp_connect"
    target_host: str | None = Field(default=None, min_length=1, max_length=255)
    target_port: int | None = Field(default=None, ge=1, le=65535)
    error_phase: ProbeErrorPhase | None = None
    source: str = Field(min_length=1, max_length=64)
    is_reachable: bool
    latency_ms: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=255)
    checked_at: datetime | None = None
    details: ProbeDetails = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: ProbeDetails) -> ProbeDetails:
        if len(value) > 32:
            raise ValueError("details must contain at most 32 keys")
        for key, item in value.items():
            if len(key) > 64:
                raise ValueError("details keys must be <= 64 chars")
            if isinstance(item, str) and len(item) > 256:
                raise ValueError("details string values must be <= 256 chars")
        serialized = json.dumps(value, ensure_ascii=False)
        if len(serialized) > 4096:
            raise ValueError("details payload is too large")
        return value


class ProbeReportOut(BaseModel):
    id: UUID
    node_id: UUID
    route_id: UUID | None
    transport_profile_id: UUID | None
    transport_kind: ProbeTransportKind | None
    probe_kind: ProbeKind
    target_host: str | None
    target_port: int | None
    error_phase: ProbeErrorPhase | None
    source: str
    is_reachable: bool
    latency_ms: int | None
    error: str | None
    checked_at: datetime
    details: ProbeDetails
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProbeSignalInternalCreate(BaseModel):
    node_id: UUID
    route_id: UUID | None = None
    transport_profile_id: UUID | None = None
    transport_kind: ProbeTransportKind | None = None
    probe_kind: ProbeKind = "tcp_connect"
    target_host: str | None = Field(default=None, min_length=1, max_length=255)
    target_port: int | None = Field(default=None, ge=1, le=65535)
    error_phase: ProbeErrorPhase | None = None
    source: str = Field(min_length=1, max_length=64)
    is_reachable: bool
    latency_ms: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=255)
    checked_at: datetime
    details: ProbeDetails = Field(default_factory=dict)


class ProbeTargetOut(BaseModel):
    node_id: UUID
    route_id: UUID | None = None
    route_name: str | None = None
    transport_profile_id: UUID | None = None
    transport_profile_name: str | None = None
    transport_kind: ProbeTransportKind | None = None
    probe_kind: ProbeKind = "tcp_connect"
    node_name: str
    region: str
    probe_client_id: str | None = None
    target_host: str
    target_port: int
    tls_sni: str | None = None
    tls_fingerprint: str | None = None
    ws_host: str | None = None
    ws_path: str | None = None
    reality_public_key: str | None = None
    reality_short_id: str | None = None
    reality_server_name: str | None = None
    flow: str | None = None


class ProbeSyntheticClientIds(BaseModel):
    reality: str | None = None
    ws: str | None = None

    @field_validator("reality", "ws", mode="before")
    @classmethod
    def normalize_optional_client_id(cls, value: str | None):
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def configured_transports(self) -> dict[ProbeTransportKind, str]:
        configured: dict[ProbeTransportKind, str] = {}
        for transport_kind, client_id in (
            ("reality", self.reality),
            ("ws", self.ws),
        ):
            if client_id is not None:
                configured[transport_kind] = client_id
        return configured


class ProbeSyntheticTransportBackends(BaseModel):
    transport_kind: ProbeTransportKind
    backend_ids: set[UUID] = Field(default_factory=set)


class ProbeSyntheticDesiredBackends(BaseModel):
    transports: dict[ProbeTransportKind, ProbeSyntheticTransportBackends] = Field(default_factory=dict)

    def add_backend(self, *, transport_kind: ProbeTransportKind, backend_id: UUID) -> None:
        transport_backends = self.transports.setdefault(
            transport_kind,
            ProbeSyntheticTransportBackends(transport_kind=transport_kind),
        )
        transport_backends.backend_ids.add(backend_id)

    def backend_ids_for(self, transport_kind: ProbeTransportKind) -> set[UUID]:
        transport_backends = self.transports.get(transport_kind)
        if transport_backends is None:
            return set()
        return set(transport_backends.backend_ids)

    def is_empty(self) -> bool:
        return not self.transports


class ProbeSyntheticReconcileResult(BaseModel):
    processed_transports: int = 0
    created_user: bool = False
    created_keys: int = 0
    reactivated_keys: int = 0
    activated_placements: int = 0
    deactivated_placements: int = 0


class ProbeDrainMigrateIn(BaseModel):
    source_backend_id: UUID
    target_backend_id: UUID | None = None
    require_recent_failure: bool = True
    max_probe_age_sec: int = Field(default=600, ge=30, le=86400)
    min_consecutive_failures: int = Field(default=1, ge=1, le=10)
    source: str | None = Field(default=None, max_length=64)
    last_migration_reason: str = Field(default="probe_failure", max_length=64)


class ProbeDrainMigrateOut(BaseModel):
    source_backend_id: UUID
    target_backend_id: UUID
    migrated_count: int
    drained: bool
    probe_report_id: UUID | None = None


class ProbeAutoDrainMigrateIn(BaseModel):
    backend_node_ids: list[UUID] | None = None
    target_backend_id: UUID | None = None
    source: str | None = Field(default=None, max_length=64)
    require_recent_failure: bool = True
    max_probe_age_sec: int = Field(default=600, ge=30, le=86400)
    min_consecutive_failures: int = Field(default=1, ge=1, le=10)
    include_already_draining: bool = False
    dry_run: bool = False
    max_nodes: int = Field(default=20, ge=1, le=200)
    last_migration_reason: str = Field(default="probe_auto_failure", max_length=64)


class ProbeAutoDrainMigrateItemOut(BaseModel):
    source_backend_id: UUID | None = None
    action: Literal["migrated", "would_migrate", "skipped", "error"]
    detail: str | None = None
    target_backend_id: UUID | None = None
    migrated_count: int = 0
    probe_report_id: UUID | None = None


class ProbeAutoDrainMigrateOut(BaseModel):
    processed: int
    migrated: int
    skipped: int
    dry_run: bool
    items: list[ProbeAutoDrainMigrateItemOut]


class ProbeCleanupOut(BaseModel):
    deleted: int = Field(ge=0)
    retention_days: int = Field(ge=1)

