from __future__ import annotations

import logging
import time

from services.balancer.rebalance import BackendRebalancer
from services.config import BackendRebalanceConfig, NatsConfig, get_settings
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("balancer-load-consumer"))


class BackendLoadRebalanceConsumer:
    def __init__(self, config: NatsConfig, *, rebalance_config: BackendRebalanceConfig | None = None):
        self._config = config
        self._cfg = rebalance_config or get_settings().backend_rebalance
        self._nats = NatsClient(config)
        self._running = False
        self._last_rebalance_monotonic = 0.0

    async def start(self):
        if not self._config.enabled:
            logger.info("backend_load_consumer_disabled")
            return

        await self._nats.connect()
        await self._nats.ensure_stream(
            name=self._config.js_traffic_stream,
            subjects=[self._config.users_traffic_subject, self._config.nodes_traffic_subject],
            max_msgs_per_subject=self._config.js_traffic_max_msgs_per_subject,
            max_age=self._config.js_traffic_max_age_s,
            duplicate_window=self._config.js_traffic_duplicate_window_s,
        )
        durable = f"{self._config.js_consumer_prefix}-balancer-load"
        await self._nats.jetstream_subscribe_durable(
            subject=self._config.nodes_traffic_subject,
            durable=durable,
            queue=durable,
            handler=self._handle_message,
            ack_wait_s=self._config.js_traffic_ack_wait_s,
            max_deliver=self._config.js_traffic_max_deliver,
        )
        self._running = True
        logger.info(
            "backend_load_consumer_started",
            subject=self._config.nodes_traffic_subject,
            durable=durable,
        )

    async def stop(self):
        if not self._running:
            return
        await self._nats.close()
        self._running = False
        logger.info("backend_load_consumer_stopped")

    async def _handle_message(self, raw_payload: bytes, msg):
        await msg.ack()

        now = time.monotonic()
        if now - self._last_rebalance_monotonic < self._cfg.debounce_sec:
            return
        self._last_rebalance_monotonic = now

        try:
            session_maker = AsyncDatabase.get_session_maker()
            async with session_maker() as session:
                moved = await BackendRebalancer(session, nats=self._nats).rebalance()
                if session.has_pending_writes():
                    await session.commit()
                else:
                    await session.rollback()
            if moved:
                logger.info("backend_load_rebalance_applied", moved=moved)
        except Exception:
            logger.exception("backend_load_rebalance_failed")
