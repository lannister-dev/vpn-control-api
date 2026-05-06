from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.users.exceptions import UserAlreadyExists, UserNotFound
from services.users.repository import UserRepository
from services.users.schemas import (
    UserCreateIn,
    UserDetailOut,
    UserInternalCreate,
    UserInternalUpdate,
    UserListOut,
    UserOut,
    UserUpdateIn,
)
from shared.database.session import AsyncDatabase
from shared.monitoring.metrics import USERS_REGISTERED_TOTAL


class UserService:
    def __init__(self, session: AsyncSession):
        self.repo = UserRepository(session)

    async def list_users(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        tag: str | None = None,
        has_debt: bool | None = None,
        has_subscription: bool | None = None,
        expiring_within_days: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> UserListOut:
        rows, total = await self.repo.list_paginated(
            search=search,
            is_active=is_active,
            tag=tag,
            has_debt=has_debt,
            has_subscription=has_subscription,
            expiring_within_days=expiring_within_days,
            limit=limit,
            offset=offset,
        )
        return UserListOut(
            items=[UserOut.model_validate(u) for u in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_user_detail(self, user_id: UUID) -> UserDetailOut:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFound(f"User {user_id} not found")

        sub_count = await self.repo.count_subscriptions(user_id)
        key_count = await self.repo.count_keys(user_id)

        data = UserOut.model_validate(user).model_dump()
        return UserDetailOut(**data, subscription_count=sub_count, key_count=key_count)

    async def create_user(self, data: UserCreateIn, *, source: str = "admin") -> UserOut:
        existing = await self.repo.get_by_telegram_id(data.telegram_id)
        if existing:
            raise UserAlreadyExists(
                f"User with telegram_id={data.telegram_id} already exists"
            )

        user = await self.repo.create(
            UserInternalCreate(
                telegram_id=data.telegram_id,
                username=data.username,
                tag=data.tag,
                description=data.description,
            ).model_dump()
        )
        USERS_REGISTERED_TOTAL.labels(source=source).inc()
        return UserOut.model_validate(user)

    async def update_user(self, user_id: UUID, data: UserUpdateIn) -> UserOut:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFound(f"User {user_id} not found")

        update_data = UserInternalUpdate.model_validate(
            data.model_dump(exclude_unset=True)
        ).model_dump(exclude_unset=True)
        if not update_data:
            return UserOut.model_validate(user)

        updated = await self.repo.update_by_id(user_id, update_data)
        return UserOut.model_validate(updated)

    async def deactivate_user(self, user_id: UUID) -> UserOut:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFound(f"User {user_id} not found")

        updated = await self.repo.update_by_id(
            user_id,
            UserInternalUpdate(is_active=False).model_dump(exclude_unset=True),
        )
        return UserOut.model_validate(updated)


def get_user_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> UserService:
    return UserService(session)
