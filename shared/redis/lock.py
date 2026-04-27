from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from services.config import get_settings
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger

settings = get_settings()
logger = StructuredLogger(logging.getLogger("redis.lock"))


class RedisTickLock:
    def __init__(
            self,
            *,
            key: str,
            ttl_sec: int | None = None,
            fail_open_if_client_unavailable: bool = False,
    ):
        self._key = key
        self._ttl_sec = int(ttl_sec or settings.redis.assignment_lock_ttl)
        self._fail_open_if_client_unavailable = fail_open_if_client_unavailable

    @asynccontextmanager
    async def hold(self):
        try:
            client = redis_client.client
        except RuntimeError:
            if self._fail_open_if_client_unavailable:
                yield True
                return
            raise

        try:
            acquired = await client.set(
                name=self._key,
                value="1",
                ex=self._ttl_sec,
                nx=True,
            )
        except Exception:
            logger.exception("redis_tick_lock_acquire_failed", key=self._key)
            yield False
            return

        if not acquired:
            yield False
            return

        try:
            yield True
        finally:
            try:
                await client.delete(self._key)
            except Exception:
                logger.exception("redis_tick_lock_release_failed", key=self._key)
