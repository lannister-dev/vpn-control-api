from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from starlette import status

from services.artifacts.exceptions import ArtifactStoreError
from services.artifacts.schemas import (
    ProfileArtifactPublishIn,
    ProfileArtifactOut, ErrorResponse, ReloadStatusResponse,
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
    summary="Publish profiles artifact",
    description=(
        "Publishes a new profiles artifact (registry payload) into the artifact store. "
    ),
    responses={
        201: {
            "description": "Profiles artifact successfully published and activated",
        },
        422: {
            "description": "Validation error (invalid artifact payload)",
        },
        500: {
            "model": ErrorResponse,
            "description": "Artifact store error (failed to persist/activate artifact)",
        },
    },
)
async def publish_profiles_artifact(
    payload: ProfileArtifactPublishIn,
    service: ProfileArtifactService = Depends(get_profile_artifact_service),
):
    try:
        return await service.publish(payload)
    except ArtifactStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/profiles/active", response_model=ProfileArtifactOut,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "No active profiles artifact found"
        },
    },
    summary="Get active VPN profiles artifact",
    description="Returns the currently active profiles artifact used for client configuration"
)
async def get_active_profiles_artifact(
        service: ProfileArtifactService = Depends(get_profile_artifact_service),
):
    try:
        return await service.get_active()
    except ArtifactStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/profiles/reload",
    response_model=ReloadStatusResponse,
    summary="Reload profiles registry from active artifact",
    description=(
        "Reloads the in-memory profiles registry using the currently active "
        "profiles artifact stored in the database. "
        "This operation is atomic and protected by a registry lock."
    ),
    responses={
        200: {
            "description": "Profiles registry successfully reloaded",
        },
        404: {
            "model": ErrorResponse,
            "description": "No active profiles artifact found",
        },
        500: {
            "model": ErrorResponse,
            "description": "Active profiles artifact is invalid or cannot be loaded",
        },
    },
)
async def reload_profiles_registry(
    service: ProfileArtifactService = Depends(get_profile_artifact_service),
):
    try:
        artifact = await service.get_active()
        async with profile_registry_lock:
            ProfileRegistry.reload_from_dict(
                artifact.artifact,
                artifact_version=artifact.version,
            )
    except ArtifactStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (ProfileRegistryError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid profiles artifact in DB: {exc}",
        ) from exc

    return ReloadStatusResponse(status="reloaded")
