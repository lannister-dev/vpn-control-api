from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import String, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth.admin.models import AdminAuditEvent, AdminSession, AdminUser
from shared.database.base_repository import BaseRepository


class AdminUserRepository(BaseRepository[AdminUser]):
    def __init__(self, session: AsyncSession):
        super().__init__(AdminUser, session)

    async def get_by_username(self, username: str) -> AdminUser | None:
        result = await self.session.execute(
            select(self.model).where(self.model.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> AdminUser | None:
        result = await self.session.execute(
            select(self.model).where(self.model.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def list_users(
        self,
        *,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AdminUser], int]:
        base = select(self.model)
        count_base = select(func.count(self.model.id))

        conditions = []
        if role is not None:
            conditions.append(self.model.role == role)
        if is_active is not None:
            conditions.append(self.model.is_active.is_(is_active))
        if search:
            term = f"%{search}%"
            conditions.append(
                or_(
                    self.model.username.ilike(term),
                    self.model.id.cast(String).ilike(term),
                    self.model.telegram_username.ilike(term),
                )
            )

        for cond in conditions:
            base = base.where(cond)
            count_base = count_base.where(cond)

        total_result = await self.session.execute(count_base)
        total = total_result.scalar() or 0

        stmt = base.order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        users = list(result.scalars().all())
        return users, total

    async def count_active_admins(self) -> int:
        result = await self.session.execute(
            select(func.count(self.model.id)).where(
                self.model.role == "admin",
                self.model.is_active.is_(True),
            )
        )
        return result.scalar() or 0


class AdminSessionRepository(BaseRepository[AdminSession]):
    def __init__(self, session: AsyncSession):
        super().__init__(AdminSession, session)

    async def get_valid_by_hash(self, session_hash: str) -> AdminSession | None:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(self.model).where(
                self.model.session_hash == session_hash,
                self.model.expires_at > now,
                self.model.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def delete_by_hash(self, session_hash: str) -> None:
        await self.session.execute(
            delete(self.model).where(self.model.session_hash == session_hash)
        )

    async def delete_expired(self) -> int:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            delete(self.model).where(self.model.expires_at <= now)
        )
        return result.rowcount or 0

    async def delete_by_user_id(self, user_id: UUID) -> int:
        result = await self.session.execute(
            delete(self.model).where(self.model.user_id == user_id)
        )
        return result.rowcount or 0

    async def list_by_user_id(self, user_id: UUID) -> list[AdminSession]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(self.model).where(
                self.model.user_id == user_id,
                self.model.expires_at > now,
                self.model.is_active.is_(True),
            ).order_by(self.model.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_by_user_id(self, user_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(func.count(self.model.id)).where(
                self.model.user_id == user_id,
                self.model.expires_at > now,
                self.model.is_active.is_(True),
            )
        )
        return result.scalar() or 0


class AdminAuditRepository(BaseRepository[AdminAuditEvent]):
    def __init__(self, session: AsyncSession):
        super().__init__(AdminAuditEvent, session)

    async def log_event(
        self,
        *,
        action: str,
        user_id: UUID | None = None,
        detail: str | None = None,
        ip_address: str | None = None,
    ) -> AdminAuditEvent:
        obj = self.model(
            action=action,
            user_id=user_id,
            detail=detail,
            ip_address=ip_address,
        )
        self.session.add(obj)
        await self.session.flush()
        return obj
