from pydantic import BaseModel, ConfigDict


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
