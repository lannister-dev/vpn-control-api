from typing import AsyncGenerator
import sqlalchemy.engine.url as SQURL
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine

from services.config import get_settings


class AsyncDatabaseSessions:
    def __init__(self):
        db = get_settings().database

        self.URL = SQURL.URL.create(
            drivername="postgresql+asyncpg",
            username=db.user,
            password=db.password,
            host=db.host,
            port=db.port,
            database=db.name
        )

        engine_kwargs = dict(
            pool_size=db.poolSize,
            max_overflow=db.poolOverflowSize,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=db.poolTimeoutSec,
            # echo_pool="debug",
            connect_args={"server_settings": {"application_name": "prod_backend"}},
        )
        self.engine = create_async_engine(self.URL, **engine_kwargs)
        self.factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    def get_url(self) -> str:
        return str(self.URL)

    def get_session_maker(self) -> async_sessionmaker[AsyncSession]:
        return self.factory

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def return_session(self) -> AsyncSession:
        return self.factory()


AsyncDatabase = AsyncDatabaseSessions()

