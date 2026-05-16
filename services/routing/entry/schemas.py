from __future__ import annotations

import hashlib
import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EntryRoutingUser(BaseModel):
    uuid: str
    flow: str = "xtls-rprx-vision"

    model_config = ConfigDict(extra="forbid")


class EntryRoutingBackend(BaseModel):
    tag: str
    node_name: str = ""
    backend_node_id: UUID
    server: str
    server_port: int = Field(ge=1, le=65535)
    uuid: str
    flow: str = ""
    reality_public_key: str = ""
    reality_short_id: str = ""
    reality_server_name: str = ""
    reality_fingerprint: str = "chrome"

    model_config = ConfigDict(extra="forbid")


class EntryRoutingRule(BaseModel):
    user_uuid: str
    outbound_tag: str

    model_config = ConfigDict(extra="forbid")


class EntryRoutingUrltestGroup(BaseModel):
    tag: str
    outbounds: list[str]
    url: str = "https://www.gstatic.com/generate_204"
    interval: str = "1m"
    tolerance: int = Field(default=50, ge=0)
    interrupt_exist_connections: bool = True

    model_config = ConfigDict(extra="forbid")


class EntryRoutingReality(BaseModel):
    private_key: str
    short_id: str
    server_name: str
    handshake_server: str
    handshake_port: int = Field(default=443, ge=1, le=65535)

    model_config = ConfigDict(extra="forbid")


class EntryRoutingSpec(BaseModel):
    node_id: str
    listen_port: int = Field(ge=1, le=65535)
    reality: EntryRoutingReality
    users: list[EntryRoutingUser] = Field(default_factory=list)
    backends: list[EntryRoutingBackend] = Field(default_factory=list)
    rules: list[EntryRoutingRule] = Field(default_factory=list)
    urltest_groups: list[EntryRoutingUrltestGroup] = Field(default_factory=list)
    final_outbound: str = "direct"

    model_config = ConfigDict(extra="forbid")

    def signature(self) -> str:
        normalized = self.model_copy(
            update={
                "users": sorted(self.users, key=lambda u: u.uuid),
                "backends": sorted(self.backends, key=lambda b: b.tag),
                "rules": sorted(self.rules, key=lambda r: (r.user_uuid, r.outbound_tag)),
                "urltest_groups": sorted(self.urltest_groups, key=lambda g: g.tag),
            }
        )
        payload = normalized.model_dump(mode="json")
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class KeyRoutingOverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend_tag: str | None = Field(default=None, max_length=128)


class KeyRoutingOverrideOut(BaseModel):
    key_id: UUID
    client_id: str
    entry_routing_override_backend_tag: str | None

    model_config = ConfigDict(from_attributes=True)


class RoutingBackendOut(BaseModel):
    tag: str
    server: str
    server_port: int

    model_config = ConfigDict(extra="forbid")


class RoutingKeyRowOut(BaseModel):
    key_id: UUID
    client_id: str
    user_id: UUID
    user_username: str | None = None
    user_telegram_id: int | None = None
    subscription_id: UUID | None = None
    transport: str
    is_revoked: bool
    override: str | None = None
    effective_backend: str | None = None

    model_config = ConfigDict(extra="forbid")


class RoutingLiveStatsByBackend(BaseModel):
    tag: str
    connections: int

    model_config = ConfigDict(extra="forbid")


class RoutingLiveStatsByEntry(BaseModel):
    entry_node_id: str
    connections: int
    unique_users: int = 0

    model_config = ConfigDict(extra="forbid")


class RoutingStateOut(BaseModel):
    backends: list[RoutingBackendOut]
    keys: list[RoutingKeyRowOut]
    live: list[RoutingLiveStatsByBackend] = []
    live_by_entry: list[RoutingLiveStatsByEntry] = []

    model_config = ConfigDict(extra="forbid")


class OverrideChange(BaseModel):
    changed: bool
    previous: str | None
    current: str | None
    key: KeyRoutingOverrideOut

    model_config = ConfigDict(extra="forbid")
