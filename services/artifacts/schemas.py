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