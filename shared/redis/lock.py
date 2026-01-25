from __future__ import annotations
from contextlib import asynccontextmanager
from services.config import get_settings
from shared.redis.client import redis_client

settings = get_settings()


@asynccontextmanager
async def redis_lock(key: str):
    ttl = settings.redis.assignment_lock_ttl
    acquired = await redis_client.client.set(
        name=key,
        value="1",
        ex=ttl,
        nx=True,
    )
    if not acquired:
        yield False
        return

    try:
        yield True
    finally:
        await redis_client.client.delete(key)
