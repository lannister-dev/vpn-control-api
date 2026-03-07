from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy import or_, String
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

    async def list_by_client_ids(
            self,
            *,
            client_ids: list[str],
            active_only: bool = True,
    ) -> list[VpnKey]:
        normalized = [item.strip() for item in client_ids if isinstance(item, str) and item.strip()]
        if not normalized:
            return []

        stmt = select(self.model).where(self.model.client_id.in_(normalized))
        if active_only:
            now = datetime.now(timezone.utc)
            stmt = stmt.where(
                self.model.is_active.is_(True),
                self.model.valid_until > now,
                or_(
                    self.model.is_revoked.is_(False),
                    self.model.is_revoked.is_(None),
                ),
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def list_with_traffic_summary(
            self,
            *,
            user_id: UUID | None = None,
            is_revoked: bool | None = None,
            search: str | None = None,
            limit: int = 50,
            offset: int = 0,
    ) -> tuple[list[VpnKey], int]:
        from sqlalchemy import func

        base = select(self.model)
        count_base = select(func.count(self.model.id))

        conditions = []
        if user_id is not None:
            conditions.append(self.model.user_id == user_id)
        if is_revoked is not None:
            conditions.append(self.model.is_revoked.is_(is_revoked))
        if search:
            term = f"%{search}%"
            conditions.append(
                or_(
                    self.model.client_id.ilike(term),
                    self.model.id.cast(String).ilike(term),
                    self.model.user_id.cast(String).ilike(term),
                )
            )

        for cond in conditions:
            base = base.where(cond)
            count_base = count_base.where(cond)

        total_result = await self.session.execute(count_base)
        total = total_result.scalar() or 0

        stmt = base.order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        keys = list(result.scalars().all())
        return keys, total


async def get_vpn_key_repository(
        session: AsyncSession = Depends(AsyncDatabase.get_session)
) -> VpnKeyRepository:
    return VpnKeyRepository(session)
