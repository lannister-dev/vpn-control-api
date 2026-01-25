from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class VpnNodeCreate(BaseModel):
    name: str
    region: str
    public_domain: str
    internal_wg_ip: str
    xray_api_port: int = 10085
    agent_port: int = 9000
    auth_token_hash: str


class VpnNodeUpdate(BaseModel):
    name: str | None = None
    region: str | None = None
    public_domain: str | None = None
    internal_wg_ip: str | None = None
    xray_api_port: int | None = None
    agent_port: int | None = None


class VpnNodeOut(BaseModel):
    id: str
    name: str
    region: str
    public_domain: str
    internal_wg_ip: str
    xray_api_port: int
    agent_port: int

    model_config = ConfigDict(from_attributes=True)


class NodeAgentStateCreate(BaseModel):
    node_id: str
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: Dict = Field(default_factory=dict)


class NodeAgentStateUpdate(BaseModel):
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: Dict = Field(default_factory=dict)


class NodeHeartbeatIn(BaseModel):
    agent_version: str
    is_healthy: bool
    details: Dict = Field(default_factory=dict)


class NodeAgentStateOut(BaseModel):
    node_id: str
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: Dict

    model_config = ConfigDict(from_attributes=True)


class NodeHeartbeatInternal(BaseModel):
    node_id: str
    agent_version: str
    is_healthy: bool
    last_seen_at: datetime
    details: Dict
