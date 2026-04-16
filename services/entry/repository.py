from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.entry.models import EntryBackendAssignment
from shared.database.base_repository import BaseRepository


class EntryBackendAssignmentRepository(BaseRepository[EntryBackendAssignment]):
    def __init__(self, session: AsyncSession):
        super().__init__(EntryBackendAssignment, session)

    async def list_by_entry(self, entry_node_id: UUID) -> list[EntryBackendAssignment]:
        stmt = (
            select(self.model)
            .where(self.model.entry_node_id == entry_node_id)
            .where(self.model.is_active.is_(True))
            .order_by(self.model.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_entry_and_backend(
        self,
        *,
        entry_node_id: UUID,
        backend_node_id: UUID,
    ) -> EntryBackendAssignment | None:
        stmt = (
            select(self.model)
            .where(self.model.entry_node_id == entry_node_id)
            .where(self.model.backend_node_id == backend_node_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
