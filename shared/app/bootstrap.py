from __future__ import annotations

import logging

from services.config import NatsConfig
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.profiles.init import bootstrap_profiles_registry
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger


def configure_root_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def connect_redis(logger: StructuredLogger) -> None:
    await redis_client.connect()
    logger.info("redis_connected")


async def bootstrap_profiles(logger: StructuredLogger) -> None:
    session_maker = AsyncDatabase.get_session_maker()
    async with session_maker() as session:
        await bootstrap_profiles_registry(session)
    logger.info("profiles_bootstrap_complete")


async def connect_nats(
    settings: NatsConfig,
    logger: StructuredLogger,
) -> NatsClient | None:
    if not settings.enabled:
        return None
    client = NatsClient(settings)
    try:
        await client.connect()
    except Exception as exc:
        logger.exception("nats_connect_failed", error=str(exc))
        return None
    logger.info("nats_connected")
    return client


async def disconnect_nats(
    client: NatsClient | None,
    logger: StructuredLogger,
) -> None:
    if client is None:
        return
    try:
        await client.close()
    except Exception:
        logger.exception("nats_close_failed")
