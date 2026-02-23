from __future__ import annotations

from typing import AsyncGenerator

import sqlalchemy.engine.url as SQURL
from sqlalchemy.sql.dml import Delete, Insert, Update
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine

from services.config import get_settings


class WriteAwareAsyncSession(AsyncSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._has_write_statements = False

    async def execute(self, statement, *args, **kwargs):
        if self._is_write_statement(statement):
            self._has_write_statements = True
        return await super().execute(statement, *args, **kwargs)

    def add(self, instance, _warn: bool = True):
        self._has_write_statements = True
        return super().add(instance, _warn=_warn)

    def add_all(self, instances):
        self._has_write_statements = True
        return super().add_all(instances)

    async def delete(self, instance):
        self._has_write_statements = True
        return await super().delete(instance)

    def has_pending_writes(self) -> bool:
        return bool(
            self._has_write_statements
            or self.new
            or self.dirty
            or self.deleted
        )

    @staticmethod
    def _is_write_statement(statement) -> bool:
        if isinstance(statement, (Insert, Update, Delete)):
            return True
        if isinstance(statement, TextClause):
            prefix = statement.text.strip().upper()
            return prefix.startswith(("INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE"))
        return False


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
        self.factory = async_sessionmaker(
            self.engine,
            class_=WriteAwareAsyncSession,
            expire_on_commit=False,
        )

    def get_url(self) -> str:
        return str(self.URL)

    def get_session_maker(self) -> async_sessionmaker[WriteAwareAsyncSession]:
        return self.factory

    async def get_session(self) -> AsyncGenerator[WriteAwareAsyncSession, None]:
        async with self.factory() as session:
            try:
                yield session
                if session.has_pending_writes():
                    await session.commit()
                else:
                    await session.rollback()
            except Exception:
                await session.rollback()
                raise

    def return_session(self) -> WriteAwareAsyncSession:
        return self.factory()


AsyncDatabase = AsyncDatabaseSessions()

