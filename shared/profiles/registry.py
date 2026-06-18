from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.schemas import (
    ProfileIn,
    ProfileMetadata,
    ProfileType,
    RealityTcpProfile,
    RealityTcpProfileIn,
    WsTlsProfile,
    WsTlsProfileIn,
    XHttpProfile,
    XHttpProfileIn,
)

ProfileInAdapter = TypeAdapter(ProfileIn)

@dataclass(frozen=True)
class ProfileConfig:
    key: str
    profile: WsTlsProfile | RealityTcpProfile | XHttpProfile


profile_registry_lock = asyncio.Lock()


class ProfileRegistry:
    _profiles: dict[str, ProfileConfig] = {}
    _artifact_version: int | None = None
    _frozen: bool = False

    @classmethod
    def register(cls, key: str, raw: dict) -> None:
        if cls._frozen:
            raise ProfileRegistryError("ProfileRegistry is frozen")

        if key in cls._profiles:
            raise ProfileRegistryError(f"Profile already registered: {key}")

        # discriminator by raw["type"]
        ptype = raw.get("type")
        if ptype == ProfileType.ws_tls.value:
            profile = WsTlsProfile.model_validate(raw)
        elif ptype == ProfileType.reality_tcp.value:
            profile = RealityTcpProfile.model_validate(raw)
        elif ptype == ProfileType.xhttp.value:
            profile = XHttpProfile.model_validate(raw)
        else:
            raise ProfileRegistryError(f"Unknown profile type for key={key}: {ptype}")

        cls._profiles[key] = ProfileConfig(key=key, profile=profile)

    @classmethod
    def freeze(cls) -> None:
        cls._frozen = True

    @classmethod
    def reset(cls) -> None:
        cls._profiles = {}
        cls._frozen = False

    @classmethod
    def get(cls, key: str) -> ProfileConfig:
        try:
            return cls._profiles[key]
        except KeyError:
            raise ProfileRegistryError(f"Profile not found: {key}")

    @classmethod
    def all_keys(cls) -> list[str]:
        return list(cls._profiles.keys())

    @classmethod
    def validate_non_empty(cls) -> None:
        if not cls._profiles:
            raise ProfileRegistryError("No profiles registered")

    @classmethod
    def bootstrap_from_dict(cls, profiles: Mapping[str, dict]) -> None:
        """
        Call on app startup. Fail-fast if invalid.
        """
        errors: list[str] = []
        for key, raw in profiles.items():
            try:
                cls.register(key, raw)
            except (ProfileRegistryError, ValidationError) as e:
                errors.append(f"{key}: {e}")

        if errors:
            raise ProfileRegistryError("Invalid profiles:\n" + "\n".join(errors))

        cls.validate_non_empty()
        cls.freeze()

    @classmethod
    def reload_from_dict(
            cls,
            profiles: Mapping[str, dict],
            *,
            artifact_version: int,
    ) -> None:
        new_profiles: dict[str, ProfileConfig] = {}
        errors: list[str] = []

        for key, raw in profiles.items():
            try:
                profile_in = ProfileInAdapter.validate_python(raw)
                metadata = ProfileMetadata(display_name=profile_in.display_name)

                if isinstance(profile_in, WsTlsProfileIn):
                    profile = WsTlsProfile(
                        type=ProfileType.ws_tls,
                        client=profile_in.client,
                        metadata=metadata,
                    )
                elif isinstance(profile_in, RealityTcpProfileIn):
                    profile = RealityTcpProfile(
                        type=ProfileType.reality_tcp,
                        client=profile_in.client,
                        metadata=metadata,
                    )
                elif isinstance(profile_in, XHttpProfileIn):
                    profile = XHttpProfile(
                        type=ProfileType.xhttp,
                        client=profile_in.client,
                        metadata=metadata,
                    )
                else:
                    raise ProfileRegistryError(
                        f"Unsupported profile type: {type(profile_in)!r}"
                    )
                new_profiles[key] = ProfileConfig(key=key, profile=profile)

            except (ValidationError, ProfileRegistryError) as exc:
                errors.append(f"{key}: {exc}")

        if errors:
            raise ProfileRegistryError(
                "Invalid profiles:\n" + "\n".join(errors)
            )
        if not new_profiles:
            raise ProfileRegistryError("No profiles registered")

        cls._profiles = new_profiles
        cls._artifact_version = artifact_version
        cls._frozen = True
