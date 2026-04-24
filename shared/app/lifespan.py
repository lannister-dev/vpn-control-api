from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from fastapi import FastAPI

from services.config import NatsConfig
from shared.app.bootstrap import (
    bootstrap_profiles,
    connect_nats,
    connect_redis,
    disconnect_nats,
)
from shared.utils.logger import StructuredLogger


LifespanHook = Callable[[FastAPI], "AsyncIterator[None] | None"]


def build_lifespan(
    *,
    logger: StructuredLogger,
    with_nats: bool = False,
    nats_settings: NatsConfig | None = None,
    ready_event: str = "app_ready",
    shutdown_event: str = "app_shutdown",
):
    if with_nats and nats_settings is None:
        raise ValueError("nats_settings is required when with_nats=True")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await connect_redis(logger)
        await bootstrap_profiles(logger)

        nats = None
        if with_nats:
            nats = await connect_nats(nats_settings, logger)
            if nats is not None:
                app.state.nats_client = nats
                app.state.nats_config = nats_settings

        logger.info(ready_event)
        try:
            yield
        finally:
            if nats is not None:
                await disconnect_nats(nats, logger)
            logger.info(shutdown_event)

    return lifespan
