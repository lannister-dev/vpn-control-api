from typing import Literal, Annotated

from pydantic import BaseModel, Field, field_validator

from shared.profiles.types import ProfileType


class ProfileMetadata(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    region_support: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_display_name(cls, v: str) -> str:
        return str(v).strip()

    @field_validator("region_support", mode="before")
    @classmethod
    def normalize_region_support(cls, v: list[str] | str | None) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        regions: list[str] = []
        for item in v:
            region = str(item).strip().lower()
            if region and region not in regions:
                regions.append(region)
        return regions


class WsTlsClientConfig(BaseModel):
    path: str = Field(min_length=1, max_length=256)
    host: str = Field(min_length=1, max_length=255)
    sni: str = Field(min_length=1, max_length=255)

    @field_validator("path")
    @classmethod
    def normalize_path(cls, v: str) -> str:
        if not v.startswith("/"):
            v = "/" + v
        return v


class RealityTcpClientConfig(BaseModel):
    sni: str = Field(min_length=1, max_length=255)
    flow: str | None = Field(default=None, min_length=1, max_length=64)
    fingerprint: str = Field(min_length=1, max_length=64)

    public_key: str = Field(min_length=16, max_length=128)
    short_id: str = Field(min_length=1, max_length=32)

    spider_x: str | None = Field(default=None, max_length=128)

    @field_validator("flow", mode="before")
    @classmethod
    def normalize_flow(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def resolve_flow(self) -> str | None:
        if self.flow:
            return self.flow
        return "xtls-rprx-vision"


class BaseProfile(BaseModel):
    type: ProfileType
    metadata: ProfileMetadata


class WsTlsProfile(BaseProfile):
    type: ProfileType = ProfileType.ws_tls
    client: WsTlsClientConfig


class RealityTcpProfile(BaseProfile):
    type: ProfileType = ProfileType.reality_tcp
    client: RealityTcpClientConfig


class NodePublic(BaseModel):
    domain: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    remark: str = Field(default="", max_length=128)
    region: str | None = Field(default=None, min_length=2, max_length=16)

    @field_validator("domain", mode="before")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        return str(v).strip()

    @field_validator("remark", mode="before")
    @classmethod
    def normalize_remark(cls, v: str | None) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("region", mode="before")
    @classmethod
    def normalize_region(cls, v: str | None) -> str | None:
        if v is None:
            return None
        region = str(v).strip().lower()
        return region or None


class InboundProfile(BaseModel):
    """
    Wrapper to allow typed union with explicit discriminator.
    """
    key: str = Field(min_length=3, max_length=64)
    value: WsTlsProfile | RealityTcpProfile


class WsTlsQuery(BaseModel):
    type: str = Field(default="ws")
    security: str = Field(default="tls")
    encryption: str = Field(default="none")

    sni: str
    host: str
    path: str

    def to_query(self) -> dict[str, str]:
        return self.model_dump(exclude_none=True)


class RealityTcpQuery(BaseModel):
    type: str = Field(default="tcp")
    security: str = Field(default="reality")
    encryption: str = Field(default="none")

    sni: str
    fp: str
    pbk: str
    sid: str
    flow: str | None = None
    spx: str | None = None

    def to_query(self) -> dict[str, str]:
        return self.model_dump(exclude_none=True)


class WsTlsProfileIn(BaseModel):
    type: Literal["ws_tls"]
    display_name: str
    client: WsTlsClientConfig


class RealityTcpProfileIn(BaseModel):
    type: Literal["reality_tcp"]
    display_name: str
    client: RealityTcpClientConfig


ProfileIn = Annotated[
    WsTlsProfileIn | RealityTcpProfileIn,
    Field(discriminator="type"),
]


class ArtifactProfile(BaseModel):
    artifact_key: str
    name: str
    protocol: str = "vless"
    network: str = Field(min_length=1, max_length=16)
    security: str = Field(min_length=1, max_length=16)
    flow: str | None = Field(default=None, max_length=64)
    reality_public_key: str | None = Field(default=None, max_length=128)
    reality_short_id: str | None = Field(default=None, max_length=32)
    reality_server_name: str | None = Field(default=None, max_length=255)
    tls_fingerprint: str = Field(default="chrome", min_length=1, max_length=64)
    grpc_service_name: str | None = Field(default=None, max_length=64)
    port: int = Field(ge=1, le=65535)


class ArtifactProfileMapResult(BaseModel):
    desired_profiles: list[ArtifactProfile]
    skipped_profiles: list[str]
    profiles_total: int
