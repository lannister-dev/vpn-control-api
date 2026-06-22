from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from services.config import NatsConfig
from services.drip.constants import DRIP_ENROLLMENT_DURABLE, TRIGGER_EVENTS
from services.drip.schemas import DripTriggerEvent
from services.drip.service import DripService
from services.notifications.constants import NOTIFICATIONS_MAX_MSGS_PER_SUBJECT
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("drip-enrollment-consumer"))


class DripEnrollmentConsumer:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nats = NatsClient(config)
        self._running = False

    async def start(self):
        if not self._config.enabled:
            logger.info("drip_enrollment_consumer_disabled")
            return
        await self._nats.connect()
        await self._nats.ensure_stream(
            name=self._config.js_notifications_stream,
            subjects=[self._config.notifications_subject],
            max_msgs_per_subject=NOTIFICATIONS_MAX_MSGS_PER_SUBJECT,
        )
        await self._nats.jetstream_subscribe_durable(
            subject=self._config.notifications_subject,
            durable=DRIP_ENROLLMENT_DURABLE,
            queue=DRIP_ENROLLMENT_DURABLE,
            handler=self._handle_message,
            ack_wait_s=self._config.js_support_ack_wait_s,
            max_deliver=self._config.js_support_max_deliver,
        )
        self._running = True
        logger.info(
            "drip_enrollment_consumer_started",
            subject=self._config.notifications_subject,
        )

    async def stop(self):
        if not self._running:
            return
        await self._nats.close()
        self._running = False
        logger.info("drip_enrollment_consumer_stopped")

    async def _handle_message(self, raw_payload: bytes, msg):
        event = self._parse(raw_payload)
        if event is None or event.kind not in TRIGGER_EVENTS:
            await msg.ack()
            return
        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            svc = DripService(
                session,
                nats_client=self._nats,
                outbound_subject=self._config.support_outbound_subject,
            )
            try:
                enrolled = await svc.enroll_for_event(
                    event_kind=event.kind, telegram_id=event.telegram_id
                )
                if enrolled:
                    await session.commit()
                    logger.info(
                        "drip_enrolled",
                        kind=event.kind,
                        telegram_id=event.telegram_id,
                        campaigns=enrolled,
                    )
            except Exception:
                logger.exception("drip_enroll_failed", kind=event.kind)
                await session.rollback()
        await msg.ack()

    @staticmethod
    def _parse(raw_payload: bytes) -> DripTriggerEvent | None:
        try:
            obj = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        try:
            return DripTriggerEvent.model_validate(obj)
        except ValidationError:
            return None
