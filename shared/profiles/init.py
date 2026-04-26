import logging

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from services.artifacts.exceptions import ArtifactStoreError
from services.artifacts.service import ProfileArtifactService
from services.config import get_settings
from shared.profiles.exceptions import ProfileRegistryError, ProfilesBootstrapError
from shared.profiles.registry import ProfileRegistry, profile_registry_lock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("bootstrap_profiles_registry"))

_settings = get_settings()

async def bootstrap_profiles_registry(session: AsyncSession) -> None:
    service = ProfileArtifactService(session)

    try:
        artifact = await service.get_active()
    except ArtifactStoreError:
        if _settings.profiles_vpn:
            logger.warning(
                "Profiles registry not initialized yet (bootstrap mode enabled)"
            )
            return
        raise ProfilesBootstrapError(
            "No active profiles artifact found"
        )

    try:
        async with profile_registry_lock:
            ProfileRegistry.reload_from_dict(
                artifact.artifact,
                artifact_version=artifact.version,
            )
    except (ProfileRegistryError, ValidationError) as exc:
        logger.exception("Failed to load profiles registry", error=str(exc))
        raise ProfilesBootstrapError(
            "Invalid profiles artifact in DB"
        ) from exc

    logger.info(
        "Profiles registry initialized",
        version=artifact.version,
        checksum=artifact.checksum,
    )