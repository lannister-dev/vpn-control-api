from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.vpn.keys.models import VpnKey
from shared.database.base_repository import BaseRepository
from shared.database.session import AsyncDatabase


class VpnKeyRepository(BaseRepository[VpnKey]):
    def __init__(self, session: AsyncSession):
        super().__init__(VpnKey, session)

    async def get_latest_active_for_user(
            self,
            *,
            user_id: UUID,
            transport: str | None = None,
    ) -> VpnKey | None:
        now = datetime.now(timezone.utc)
        stmt = select(self.model).where(
            self.model.user_id == user_id,
            self.model.is_active.is_(True),
            self.model.is_revoked.is_(False),
            self.model.valid_until > now,
        )
        if transport is not None:
            stmt = stmt.where(self.model.transport == transport)

        stmt = stmt.order_by(self.model.valid_until.desc(), self.model.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


async def get_vpn_key_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> VpnKeyRepository:
    return VpnKeyRepository(session)
