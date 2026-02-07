from __future__ import annotations
import hashlib
import json

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.artifacts.exceptions import ArtifactStoreError
from services.artifacts.models import ProfileArtifact
from services.artifacts.repository import ProfileArtifactRepository
from services.artifacts.schemas import ProfileArtifactCreate, ProfileArtifactPublishIn
from shared.database.session import AsyncDatabase


class ProfileArtifactService:
    def __init__(self, session: AsyncSession):
        self.repository = ProfileArtifactRepository(session)
        self.session = session

    async def publish(self, data: ProfileArtifactPublishIn) -> ProfileArtifact:
        payload = json.dumps(data.artifact, sort_keys=True).encode()
        checksum = hashlib.sha256(payload).hexdigest()

        version = await self.repository.get_latest_version() + 1

        await self.repository.deactivate_all()

        artifact = await self.repository.create(
            ProfileArtifactCreate(
                version=version,
                checksum=checksum,
                artifact=data.artifact
            ).model_dump()
        )

        return artifact

    async def get_active(self):
        artifact = await self.repository.get_active()
        if not artifact:
            raise ArtifactStoreError("No active profiles artifact")
        return artifact

    async def get_active_payload(self) -> dict:
        artifact = await self.get_active()
        return artifact.artifact


def get_profile_artifact_service(
        session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> ProfileArtifactService:
    return ProfileArtifactService(session)
