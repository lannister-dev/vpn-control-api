from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Mapping

from pydantic import ValidationError

from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.types import WsTlsProfile, RealityTcpProfile, ProfileType


@dataclass(frozen=True)
class ProfileConfig:
    key: str
    profile: WsTlsProfile | RealityTcpProfile


profile_registry_lock = asyncio.Lock()


class ProfileRegistry:
    _profiles: dict[str, ProfileConfig] = {}
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
    def reload_from_dict(cls, profiles: Mapping[str, dict]) -> None:
        new_profiles: dict[str, ProfileConfig] = {}
        errors: list[str] = []

        for key, raw in profiles.items():
            try:
                ptype = raw.get("type")
                if ptype == ProfileType.ws_tls.value:
                    profile = WsTlsProfile.model_validate(raw)
                elif ptype == ProfileType.reality_tcp.value:
                    profile = RealityTcpProfile.model_validate(raw)
                else:
                    raise ProfileRegistryError(f"Unknown profile type: {ptype}")

                new_profiles[key] = ProfileConfig(key=key, profile=profile)
            except (ProfileRegistryError, ValidationError) as e:
                errors.append(f"{key}: {e}")

        if errors:
            raise ProfileRegistryError("Invalid profiles:\n" + "\n".join(errors))

        if not new_profiles:
            raise ProfileRegistryError("No profiles registered")

        cls._profiles = new_profiles
        cls._frozen = True
