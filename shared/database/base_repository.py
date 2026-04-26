from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.base_model import Base

ModelType = TypeVar('ModelType', bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def list(self, *, limit: int | None = None) -> Sequence[ModelType]:
        stmt = select(self.model).order_by(self.model.id.desc())
        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, item_id: Any) -> ModelType | None:
        result = await self.session.execute(
            select(self.model).where(self.model.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_one_by(self, **filters) -> ModelType | None:
        result = await self.session.execute(
            select(self.model).filter_by(**filters)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> ModelType:
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update_by_id(self, item_id: Any, data: dict) -> ModelType | None:
        await self.session.execute(
            update(self.model)
            .where(self.model.id == item_id)
            .values(**data)
        )
        return await self.get_by_id(item_id)

    async def delete_by_id(self, item_id: Any) -> None:
        await self.session.execute(
            delete(self.model).where(self.model.id == item_id)
        )
