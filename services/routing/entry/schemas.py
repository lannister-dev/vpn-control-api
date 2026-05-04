from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field


class EntryRoutingUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uuid: str
    flow: str = "xtls-rprx-vision"


class EntryRoutingBackend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str
    server: str
    server_port: int = Field(ge=1, le=65535)
    uuid: str
    flow: str = ""
    reality_public_key: str = ""
    reality_short_id: str = ""
    reality_server_name: str = ""
    reality_fingerprint: str = "chrome"


class EntryRoutingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_uuid: str
    outbound_tag: str


class EntryRoutingReality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    private_key: str
    short_id: str
    server_name: str
    handshake_server: str
    handshake_port: int = Field(default=443, ge=1, le=65535)


class EntryRoutingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    listen_port: int = Field(ge=1, le=65535)
    reality: EntryRoutingReality
    users: list[EntryRoutingUser] = Field(default_factory=list)
    backends: list[EntryRoutingBackend] = Field(default_factory=list)
    rules: list[EntryRoutingRule] = Field(default_factory=list)
    final_outbound: str = "direct"

    def signature(self) -> str:
        normalized = self.model_copy(
            update={
                "users": sorted(self.users, key=lambda u: u.uuid),
                "backends": sorted(self.backends, key=lambda b: b.tag),
                "rules": sorted(self.rules, key=lambda r: (r.user_uuid, r.outbound_tag)),
            }
        )
        payload = normalized.model_dump(mode="json")
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
