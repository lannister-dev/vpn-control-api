from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.admin_status.schemas import RuntimeReadinessCheckOut, RuntimeReadinessOut
from shared.database.session import AsyncDatabase
from shared.redis.client import RedisClient, redis_client


class RuntimeReadinessService:
    def __init__(
            self,
            *,
            session_maker: async_sessionmaker[AsyncSession] | None = None,
            redis: RedisClient | None = None,
    ):
        self._session_maker = session_maker or AsyncDatabase.get_session_maker()
        self._redis = redis or redis_client

    async def get_readiness(self) -> RuntimeReadinessOut:
        checks = [
            await self._check_database(),
            await self._check_redis(),
        ]
        return RuntimeReadinessOut(
            generated_at=datetime.now(timezone.utc),
            ready=all(check.ok for check in checks),
            checks=checks,
        )

    async def _check_database(self) -> RuntimeReadinessCheckOut:
        try:
            async with self._session_maker() as session:
                await session.execute(text("SELECT 1"))
                await session.rollback()
        except Exception as exc:
            return RuntimeReadinessCheckOut(
                name="database",
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
            )
        return RuntimeReadinessCheckOut(
            name="database",
            ok=True,
            detail="ok",
        )

    async def _check_redis(self) -> RuntimeReadinessCheckOut:
        try:
            await self._redis.client.ping()
        except Exception as exc:
            return RuntimeReadinessCheckOut(
                name="redis",
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
            )
        return RuntimeReadinessCheckOut(
            name="redis",
            ok=True,
            detail="ok",
        )
