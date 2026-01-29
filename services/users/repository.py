from sqlalchemy.ext.asyncio import AsyncSession
from services.users.models import User
from shared.database.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)
