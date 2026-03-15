from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, Field

from shared.profiles.schemas import WsTlsProfileIn, RealityTcpProfileIn


class ProfileArtifactPublishIn(BaseModel):
    artifact: Dict[str, dict] = Field(
        ...,
        min_length=1,
        description=(
            "Profiles registry payload keyed by profile key. "
            "Each value must be a valid profile object with discriminator field 'type'."
        ),
        examples=[
            {
                "ws_tls_v1": {
                    "type": "ws_tls",
                    "display_name": "CDN WS TLS",
                    "client": {
                        "path": "/ws",
                        "host": "cdn.example.com",
                        "sni": "cdn.example.com"
                    }
                },
                "reality_tcp_v1": {
                    "type": "reality_tcp",
                    "display_name": "Reality TCP",
                    "client": {
                        "sni": "www.cloudflare.com",
                        "flow": "xtls-rprx-vision",
                        "fingerprint": "chrome",
                        "public_key": "PUBLIC_KEY",
                        "short_id": "abcd1234"
                    }
                }
            }
        ]
    )

    @field_validator("artifact")
    @classmethod
    def validate_artifact(cls, artifact: Dict[str, dict]) -> Dict[str, dict]:
        if not artifact:
            raise ValueError("artifact must not be empty")

        errors: list[str] = []

        for key, raw in artifact.items():
            if not isinstance(raw, dict):
                errors.append(f"{key}: profile value must be an object")
                continue

            ptype = raw.get("type")
            try:
                if ptype == "ws_tls":
                    WsTlsProfileIn.model_validate(raw)
                elif ptype == "reality_tcp":
                    RealityTcpProfileIn.model_validate(raw)
                else:
                    raise ValueError(f"unknown profile type: {ptype}")
            except (ValidationError, ValueError) as exc:
                errors.append(f"{key}: {exc}")

        if errors:
            raise ValueError("Invalid profiles:\n" + "\n".join(errors))

        return artifact


class ProfileArtifactCreate(BaseModel):
    version: int
    artifact: Dict[str, Any]
    checksum: str


class ProfileArtifactUpdate(BaseModel):
    is_active: bool | None = None


class ProfileArtifactOut(BaseModel):
    id: UUID
    version: int
    checksum: str
    artifact: Dict[str, Any]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ReloadStatusResponse(BaseModel):
    status: str

class ErrorResponse(BaseModel):
    detail: str


class ArtifactRoutesBootstrapIn(BaseModel):
    backend_node_ids: list[UUID] | None = Field(
        default=None,
        description="Optional explicit list of node ids to bootstrap.",
    )
    include_reality_tcp: bool = True
    include_ws_tls: bool = False
    default_reality_port: int = Field(default=443, ge=1, le=65535)
    default_ws_port: int = Field(default=443, ge=1, le=65535)
    profile_port_overrides: Dict[str, int] = Field(default_factory=dict)
    route_base_weight: int = Field(default=50, ge=0, le=100)
    recover_unhealthy_routes: bool = True
    expected_backends_selected: int | None = Field(
        default=None,
        ge=1,
        description="Optional assertion for number of eligible nodes selected.",
    )
    expected_profiles_selected: int | None = Field(
        default=None,
        ge=1,
        description="Optional assertion for number of eligible profiles selected.",
    )
    expected_routes_total: int | None = Field(
        default=None,
        ge=0,
        description="Optional assertion for matrix size (backends_selected * profiles_selected).",
    )
    dry_run: bool = False

    @field_validator("profile_port_overrides")
    @classmethod
    def validate_profile_port_overrides(cls, value: Dict[str, int]) -> Dict[str, int]:
        normalized: Dict[str, int] = {}
        for raw_key, raw_port in value.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("profile_port_overrides keys must be non-empty")
            port = int(raw_port)
            if port < 1 or port > 65535:
                raise ValueError(f"Invalid port for profile {key!r}: {port}")
            normalized[key] = port
        return normalized


class ArtifactRoutesBootstrapOut(BaseModel):
    artifact_version: int
    dry_run: bool
    backends_selected: int
    profiles_total: int
    profiles_selected: int
    routes_total: int
    transport_profiles_created: int
    transport_profiles_updated: int
    transport_profiles_reactivated: int
    routes_created: int
    routes_updated: int
    routes_reactivated: int
    skipped_profiles: list[str]
