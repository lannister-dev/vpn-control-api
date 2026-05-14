from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.zones.exceptions import ZoneAlreadyExists, ZoneNotFound
from services.zones.repository import ZoneRepository
from services.zones.schemas import (
    ZoneCreateIn,
    ZoneListOut,
    ZoneOut,
    ZoneUpdateIn,
)
from shared.database.session import AsyncDatabase


class ZoneService:
    def __init__(self, session: AsyncSession):
        self.repo = ZoneRepository(session)

    async def list_zones(self, active_only: bool = False) -> ZoneListOut:
        rows, total = await self.repo.list_all(active_only=active_only)
        return ZoneListOut(
            items=[ZoneOut.model_validate(z) for z in rows],
            total=total,
        )

    async def get_zone(self, code: str) -> ZoneOut:
        zone = await self.repo.get_by_code(code)
        if not zone:
            raise ZoneNotFound(f"Zone '{code}' not found")
        return ZoneOut.model_validate(zone)

    async def create_zone(self, data: ZoneCreateIn) -> ZoneOut:
        if await self.repo.get_by_code(data.code):
            raise ZoneAlreadyExists(f"Zone '{data.code}' already exists")
        zone = await self.repo.create(data.model_dump())
        return ZoneOut.model_validate(zone)

    async def update_zone(self, code: str, data: ZoneUpdateIn) -> ZoneOut:
        zone = await self.repo.get_by_code(code)
        if not zone:
            raise ZoneNotFound(f"Zone '{code}' not found")
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return ZoneOut.model_validate(zone)
        updated = await self.repo.update_by_id(zone.id, update_data)
        return ZoneOut.model_validate(updated)

    async def delete_zone(self, code: str) -> ZoneOut:
        zone = await self.repo.get_by_code(code)
        if not zone:
            raise ZoneNotFound(f"Zone '{code}' not found")
        updated = await self.repo.update_by_id(zone.id, {"is_active": False})
        return ZoneOut.model_validate(updated)

    async def reorder(self, codes: list[str]) -> int:
        if not codes:
            return 0
        return await self.repo.reorder_by_codes(codes)


def get_zone_service(session: AsyncSession = Depends(AsyncDatabase.get_session)) -> ZoneService:
    return ZoneService(session)
