import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.keys.models import Key
from src.database.base_class import BaseService
from src.database.session import session_handler
from src.database.users.models import User
from src.database.users.schemas import UserCreate


class UserService(BaseService[User]):
    def __init__(self):
        super().__init__(User)

    async def check_user_and_add(self, telegram_id: int):
        user = await self.get_user_by_telegram_id(telegram_id)
        if not user:
            task = asyncio.create_task(
                user_service.create(
                    UserCreate(telegram_id=telegram_id)
                )
            )

    @session_handler
    async def get_user_by_telegram_id(self, session, telegram_id: int):
        try:
            user = await session.execute(
                select(self.model).filter_by(telegram_id=telegram_id)
            )
            user = user.scalar()
            return user
        except Exception as e:
            logging.error(e)
            return None

    @session_handler
    async def get_all_user_keys(self, session, user_id):
        result = await session.execute(
            select(Key)
            .where(Key.user_id == user_id)
            .options(selectinload(Key.server))
        )
        return result.scalars().all()


user_service = UserService()
