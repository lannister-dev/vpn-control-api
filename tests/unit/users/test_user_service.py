from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.users.exceptions import UserAlreadyExists, UserNotFound
from services.users.schemas import UserCreateIn, UserUpdateIn
from services.users.service import UserService


def _make_user(
    *,
    telegram_id: int = 123456,
    username: str | None = "testuser",
    balance: Decimal = Decimal("0.00"),
    is_active: bool = True,
    tag: str | None = None,
    description: str | None = None,
):
    return SimpleNamespace(
        id=uuid4(),
        telegram_id=telegram_id,
        username=username,
        balance=balance,
        is_active=is_active,
        tag=tag,
        description=description,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture()
def service(async_session):
    svc = UserService(async_session)
    svc.repo = AsyncMock()
    return svc


class TestUserServiceCreate:
    async def test_create_user_success(self, service):
        service.repo.get_by_telegram_id.return_value = None
        user = _make_user(telegram_id=999)
        service.repo.create.return_value = user

        result = await service.create_user(UserCreateIn(telegram_id=999))
        assert result.telegram_id == 999
        service.repo.create.assert_awaited_once()

    async def test_create_user_duplicate_raises(self, service):
        service.repo.get_by_telegram_id.return_value = _make_user()
        with pytest.raises(UserAlreadyExists):
            await service.create_user(UserCreateIn(telegram_id=123456))


class TestUserServiceGet:
    async def test_get_user_detail(self, service):
        user = _make_user()
        service.repo.get_by_id.return_value = user
        service.repo.count_subscriptions.return_value = 2
        service.repo.count_keys.return_value = 4

        result = await service.get_user_detail(user.id)
        assert result.subscription_count == 2
        assert result.key_count == 4

    async def test_get_user_detail_not_found(self, service):
        service.repo.get_by_id.return_value = None
        with pytest.raises(UserNotFound):
            await service.get_user_detail(uuid4())


class TestUserServiceUpdate:
    async def test_update_user_success(self, service):
        user = _make_user()
        updated = _make_user(username="newname")
        service.repo.get_by_id.return_value = user
        service.repo.update_by_id.return_value = updated

        result = await service.update_user(user.id, UserUpdateIn(username="newname"))
        assert result.username == "newname"

    async def test_update_user_empty_payload(self, service):
        user = _make_user()
        service.repo.get_by_id.return_value = user
        result = await service.update_user(user.id, UserUpdateIn())
        assert result.id == user.id
        service.repo.update_by_id.assert_not_awaited()

    async def test_update_user_not_found(self, service):
        service.repo.get_by_id.return_value = None
        with pytest.raises(UserNotFound):
            await service.update_user(uuid4(), UserUpdateIn(username="x"))


class TestUserServiceDeactivate:
    async def test_deactivate_success(self, service):
        user = _make_user(is_active=True)
        deactivated = _make_user(is_active=False)
        service.repo.get_by_id.return_value = user
        service.repo.update_by_id.return_value = deactivated

        result = await service.deactivate_user(user.id)
        assert result.is_active is False

    async def test_deactivate_not_found(self, service):
        service.repo.get_by_id.return_value = None
        with pytest.raises(UserNotFound):
            await service.deactivate_user(uuid4())


class TestUserServiceList:
    async def test_list_users_paginated(self, service):
        users = [_make_user(telegram_id=i) for i in range(3)]
        service.repo.list_paginated.return_value = (users, 3)

        result = await service.list_users(limit=50, offset=0)
        assert result.total == 3
        assert len(result.items) == 3
        assert result.limit == 50
        assert result.offset == 0
