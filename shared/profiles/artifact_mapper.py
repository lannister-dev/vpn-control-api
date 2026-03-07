from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from pydantic import TypeAdapter, ValidationError

from shared.profiles.schemas import (
    ArtifactProfileMapResult,
    ArtifactProfile,
    ProfileIn,
    RealityTcpProfileIn,
    WsTlsProfileIn,
)

ProfileInAdapter = TypeAdapter(ProfileIn)


class ArtifactProfileMapper:
    def __init__(
            self,
            *,
            include_reality_tcp: bool = True,
            include_ws_tls: bool = False,
            default_reality_port: int = 443,
            default_ws_port: int = 443,
            profile_port_overrides: Mapping[str, int] | None = None,
    ):
        self.include_reality_tcp = include_reality_tcp
        self.include_ws_tls = include_ws_tls
        self.default_reality_port = int(default_reality_port)
        self.default_ws_port = int(default_ws_port)
        self.profile_port_overrides = dict(profile_port_overrides or {})

    def map(self, artifact_payload: Mapping[str, Any]) -> ArtifactProfileMapResult:
        desired: list[ArtifactProfile] = []
        skipped: list[str] = []
        used_names: set[str] = set()

        for raw_key, raw_profile in sorted(artifact_payload.items(), key=lambda item: str(item[0])):
            key = str(raw_key).strip()
            if not key:
                skipped.append("<empty-key>: skipped (empty key)")
                continue
            if not isinstance(raw_profile, dict):
                skipped.append(f"{key}: skipped (profile value must be an object)")
                continue

            transport_name = self.normalize_name(key=key, max_len=100)
            if transport_name in used_names:
                skipped.append(f"{key}: skipped (normalized transport name collision: {transport_name})")
                continue

            try:
                profile_in = ProfileInAdapter.validate_python(raw_profile)
            except ValidationError as exc:
                skipped.append(f"{key}: skipped (invalid profile payload: {exc})")
                continue

            if isinstance(profile_in, RealityTcpProfileIn):
                if not self.include_reality_tcp:
                    skipped.append(f"{key}: skipped by include_reality_tcp=false")
                    continue
                port = int(self.profile_port_overrides.get(key, self.default_reality_port))
                desired.append(
                    ArtifactProfile(
                        artifact_key=key,
                        name=transport_name,
                        protocol="vless",
                        network="tcp",
                        security="reality",
                        flow=profile_in.client.flow,
                        reality_public_key=profile_in.client.public_key,
                        reality_short_id=profile_in.client.short_id,
                        reality_server_name=profile_in.client.sni,
                        tls_fingerprint=profile_in.client.fingerprint,
                        grpc_service_name=None,
                        port=port,
                    )
                )
                used_names.add(transport_name)
                continue

            if isinstance(profile_in, WsTlsProfileIn):
                if not self.include_ws_tls:
                    skipped.append(f"{key}: skipped by include_ws_tls=false")
                    continue
                port = int(self.profile_port_overrides.get(key, self.default_ws_port))
                desired.append(
                    ArtifactProfile(
                        artifact_key=key,
                        name=transport_name,
                        protocol="vless",
                        network="ws",
                        security="tls",
                        flow=None,
                        reality_public_key=None,
                        reality_short_id=None,
                        reality_server_name=None,
                        tls_fingerprint="chrome",
                        grpc_service_name=None,
                        port=port,
                    )
                )
                used_names.add(transport_name)
                continue

            skipped.append(f"{key}: skipped (unsupported profile type)")

        return ArtifactProfileMapResult(
            desired_profiles=desired,
            skipped_profiles=skipped,
            profiles_total=len(artifact_payload),
        )

    @staticmethod
    def normalize_name(*, key: str, max_len: int) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", key.strip().lower())
        normalized = re.sub(r"-{2,}", "-", normalized).strip("-_")
        if not normalized:
            normalized = "bootstrap"
        if len(normalized) <= max_len:
            return normalized
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
        trim_len = max_len - 9
        return f"{normalized[:trim_len]}-{digest}"
