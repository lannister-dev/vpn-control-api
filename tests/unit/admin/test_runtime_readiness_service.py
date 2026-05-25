from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.admin.status.runtime_service import RuntimeReadinessService


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _SessionContext(self._session)


class _RedisWrapper:
    def __init__(self, client):
        self.client = client


@pytest.mark.asyncio
async def test_runtime_readiness_ready_when_dependencies_are_ok():
    session = AsyncMock()
    redis_client = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)

    service = RuntimeReadinessService(
        session_maker=_SessionMaker(session),
        redis=_RedisWrapper(redis_client),
    )

    out = await service.get_readiness()

    assert out.ready is True
    assert [check.name for check in out.checks] == ["database", "redis"]
    assert all(check.ok for check in out.checks)
    session.execute.assert_awaited_once()
    session.rollback.assert_awaited_once()
    redis_client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_readiness_not_ready_when_database_check_fails():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db down"))
    redis_client = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)

    service = RuntimeReadinessService(
        session_maker=_SessionMaker(session),
        redis=_RedisWrapper(redis_client),
    )

    out = await service.get_readiness()

    assert out.ready is False
    db_check = next(item for item in out.checks if item.name == "database")
    assert db_check.ok is False
    assert "db down" in db_check.detail


@pytest.mark.asyncio
async def test_runtime_readiness_not_ready_when_redis_check_fails():
    session = AsyncMock()
    redis_client = AsyncMock()
    redis_client.ping = AsyncMock(side_effect=RuntimeError("redis down"))

    service = RuntimeReadinessService(
        session_maker=_SessionMaker(session),
        redis=_RedisWrapper(redis_client),
    )

    out = await service.get_readiness()

    assert out.ready is False
    redis_check = next(item for item in out.checks if item.name == "redis")
    assert redis_check.ok is False
    assert "redis down" in redis_check.detail
