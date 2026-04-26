from __future__ import annotations

import json
import logging

from services.config import NatsConfig
from services.traffic.nodes.schemas import NodeTrafficIn
from services.traffic.nodes.service import NodeTrafficService
from shared.database.session import AsyncDatabase
from services.nats_dedup.repository import NatsMessageDedupRepository
from shared.nats.client import NatsClient
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("node-traffic-nats-consumer"))


class NodeTrafficNatsConsumer:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nats = NatsClient(config)
        self._running = False

    async def start(self):
        if not self._config.enabled:
            logger.info("nodes_traffic_consumer_disabled")
            return

        await self._nats.connect()
        await self._nats.ensure_stream(
            name=self._config.js_traffic_stream,
            subjects=[self._config.users_traffic_subject, self._config.nodes_traffic_subject],
            max_msgs_per_subject=self._config.js_traffic_max_msgs_per_subject,
            max_age=self._config.js_traffic_max_age_s,
            duplicate_window=self._config.js_traffic_duplicate_window_s,
        )
        await self._nats.jetstream_subscribe_durable(
            subject=self._config.nodes_traffic_subject,
            durable=self._config.js_traffic_nodes_durable,
            queue=self._config.nodes_traffic_queue,
            handler=self._handle_message,
            ack_wait_s=self._config.js_traffic_ack_wait_s,
            max_deliver=self._config.js_traffic_max_deliver,
        )
        self._running = True
        logger.info(
            "nodes_traffic_consumer_started",
            subject=self._config.nodes_traffic_subject,
            durable=self._config.js_traffic_nodes_durable,
            queue=self._config.nodes_traffic_queue,
        )

    async def stop(self):
        if not self._running:
            return
        await self._nats.close()
        self._running = False
        logger.info("nodes_traffic_consumer_stopped")

    async def _handle_message(self, raw_payload: bytes, msg):
        items = self._parse_payload(raw_payload)
        if not items:
            await msg.ack()
            return

        msg_id = (msg.headers or {}).get("Nats-Msg-Id") if hasattr(msg, "headers") else None

        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            if msg_id:
                dedup = NatsMessageDedupRepository(session)
                claimed = await dedup.claim(subject=msg.subject, msg_id=msg_id)
                if not claimed:
                    logger.info(
                        "nodes_traffic_msg_duplicate_skipped",
                        subject=msg.subject,
                        msg_id=msg_id,
                    )
                    await msg.ack()
                    return
            service = NodeTrafficService(session)
            await service.ingest(items)
            if session.has_pending_writes():
                await session.commit()
            else:
                await session.rollback()
        await msg.ack()

    @staticmethod
    def _parse_payload(raw_payload: bytes) -> list[NodeTrafficIn]:
        try:
            payload_obj = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("nodes_traffic_payload_invalid", error=str(exc))
            return []

        if not isinstance(payload_obj, list):
            logger.warning("nodes_traffic_payload_not_list")
            return []

        items: list[NodeTrafficIn] = []
        for item in payload_obj:
            if not isinstance(item, dict):
                continue
            try:
                items.append(NodeTrafficIn.model_validate(item))
            except Exception:
                continue
        return items
