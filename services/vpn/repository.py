from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.vpn.models import KeyAssignment
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class KeyAssignmentRepository(BaseRepository[KeyAssignment]):
    def __init__(self, session: AsyncSession):
        super().__init__(KeyAssignment, session)


async def get_key_assignments_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> KeyAssignmentRepository:
    return KeyAssignmentRepository(session)
