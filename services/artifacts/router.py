from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from starlette import status

from services.artifacts.schemas import (
    ProfileArtifactPublishIn,
    ProfileArtifactOut,
)
from services.artifacts.service import (
    ProfileArtifactService,
    get_profile_artifact_service,
)
from services.auth.dependencies import admin_auth
from shared.profiles.exceptions import ProfileRegistryError
from shared.profiles.registry import ProfileRegistry, profile_registry_lock

router = APIRouter(
    prefix="/artifacts",
    tags=["Artifacts"],
    dependencies=[Depends(admin_auth)],
)


@router.post(
    "/profiles/publish",
    response_model=ProfileArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
async def publish_profiles_artifact(
        payload: ProfileArtifactPublishIn,
        service: ProfileArtifactService = Depends(get_profile_artifact_service),
):
    return await service.publish(payload)


@router.get("/profiles/active", response_model=ProfileArtifactOut)
async def get_active_profiles_artifact(
        service: ProfileArtifactService = Depends(get_profile_artifact_service),
):
    return await service.get_active()


@router.post("/profiles/reload")
async def reload_profiles_registry(
        service: ProfileArtifactService = Depends(get_profile_artifact_service),
):
    artifact = await service.get_active()
    try:
        async with profile_registry_lock:
            ProfileRegistry.reload_from_dict(artifact.artifact)
    except (ProfileRegistryError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid profiles artifact in DB: {exc}",
        ) from exc
    return {"status": "reloaded"}
