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
        payload = {
            "node_id": self.node_id,
            "listen_port": self.listen_port,
            "users": sorted(u.uuid for u in self.users),
            "backends": [
                {"tag": b.tag, "server": b.server, "port": b.server_port, "uuid": b.uuid, "flow": b.flow}
                for b in sorted(self.backends, key=lambda x: x.tag)
            ],
            "rules": sorted([(r.user_uuid, r.outbound_tag) for r in self.rules]),
            "reality": {
                "private_key": self.reality.private_key,
                "short_id": self.reality.short_id,
                "server_name": self.reality.server_name,
            },
            "final": self.final_outbound,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
