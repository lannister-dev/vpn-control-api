from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.artifacts.models import ProfileArtifact
from shared.database.base_repository import BaseRepository


class ProfileArtifactRepository(BaseRepository[ProfileArtifact]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProfileArtifact, session)

    async def get_active(self) -> ProfileArtifact | None:
        return await self.get_one_by(is_active=True)

    async def deactivate_all(self) -> None:
        await self.session.execute(
            update(ProfileArtifact)
            .where(ProfileArtifact.is_active.is_(True))
            .values(is_active=False)
        )

    async def get_latest_version(self) -> int:
        result = await self.session.execute(
            select(ProfileArtifact.version)
            .order_by(ProfileArtifact.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none() or 0