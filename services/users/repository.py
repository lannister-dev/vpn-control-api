from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.users.models import User
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)


async def get_user_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> UserRepository:
    return UserRepository(session)
