from __future__ import annotations

import logging
from typing import Optional
import redis.asyncio as redis

from services.config import get_settings
from shared.utils import logger

logger = logger.StructuredLogger(logging.getLogger("redis.client"))


class RedisClient:
    def __init__(self, url: str):
        self._url = url
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        try:
            self._client = redis.from_url(
                self._url,
                decode_responses=True,
            )
            await self._client.ping()
            logger.info("Redis connected")
        except Exception:
            logger.exception("Redis connection failed")
            raise

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis client is not initialized")
        return self._client


_settings = get_settings()
redis_client = RedisClient(url=_settings.redis.broker_url)
