from __future__ import annotations

import logging

from services.config import NatsConfig
from services.traffic.service import UserTrafficService
from shared.database.session import AsyncDatabase
from shared.nats.nats import NatsClient
from shared.utils.logger import StructuredLogger


logger_traffic_consumer = StructuredLogger(logging.getLogger("traffic-nats-consumer"))


class UserTrafficNatsConsumer:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nats = NatsClient(config)
        self._running = False

    async def start(self) -> None:
        if not self._config.enabled:
            logger_traffic_consumer.info("users_traffic_consumer_disabled")
            return

        await self._nats.connect()
        await self._nats.subscribe(
            subject=self._config.users_traffic_subject,
            queue=self._config.users_traffic_queue,
            handler=self._handle_message,
        )
        self._running = True
        logger_traffic_consumer.info(
            "users_traffic_consumer_started",
            subject=self._config.users_traffic_subject,
            queue=self._config.users_traffic_queue,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        await self._nats.close()
        self._running = False
        logger_traffic_consumer.info("users_traffic_consumer_stopped")

    async def _handle_message(self, raw_payload: bytes) -> None:
        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            service = UserTrafficService(session)
            await service.ingest_users_traffic(raw_payload)
            if session.has_pending_writes():
                await session.commit()
            else:
                await session.rollback()
