from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from services.admin.transport.repository import NatsMessageDedupRepository
from services.auth.admin.repository import AdminUserRepository
from services.config import NatsConfig, get_settings
from services.notifications.constants import NOTIFICATIONS_MAX_MSGS_PER_SUBJECT
from services.notifications.service import NotificationService
from services.support.constants import DRIP_ENROLLMENT_DURABLE, DRIP_TRIGGER_EVENTS
from services.support.emoji_assets import (
    CustomEmojiResolver,
    TelegramMediaResolver,
    custom_emoji_entities_to_html,
)
from services.support.repository import SupportMessageRepository
from services.support.schemas import (
    BroadcastAudience,
    BroadcastStatus,
    DripTriggerEvent,
    SupportInboundMessage,
    SupportSentAck,
)
from services.support.service import SupportService
from services.users.repository import UserRepository
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("support-nats-consumer"))


class SupportInboundConsumer:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nats = NatsClient(config)
        self._running = False

    async def start(self):
        if not self._config.enabled:
            logger.info("support_consumer_disabled")
            return

        await self._nats.connect()
        await self._nats.ensure_stream(
            name=self._config.js_support_stream,
            subjects=[self._config.support_inbound_subject, self._config.support_outbound_subject],
            max_msgs_per_subject=self._config.js_support_max_msgs_per_subject,
            max_age=self._config.js_support_max_age_s,
            duplicate_window=self._config.js_support_duplicate_window_s,
        )
        await self._nats.jetstream_subscribe_durable(
            subject=self._config.support_inbound_subject,
            durable=self._config.support_inbound_queue,
            queue=self._config.support_inbound_queue,
            handler=self._handle_message,
            ack_wait_s=self._config.js_support_ack_wait_s,
            max_deliver=self._config.js_support_max_deliver,
        )
        self._running = True
        logger.info(
            "support_consumer_started",
            subject=self._config.support_inbound_subject,
            queue=self._config.support_inbound_queue,
        )

    async def stop(self):
        if not self._running:
            return
        await self._nats.close()
        self._running = False
        logger.info("support_consumer_stopped")

    async def _handle_message(self, raw_payload: bytes, msg):
        parsed = self._parse_payload(raw_payload)
        if not parsed:
            await msg.ack()
            return

        msg_id = (msg.headers or {}).get("Nats-Msg-Id") if hasattr(msg, "headers") else None

        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            if msg_id:
                dedup = NatsMessageDedupRepository(session)
                claimed = await dedup.claim(subject=msg.subject, msg_id=msg_id)
                if not claimed:
                    logger.info("support_msg_duplicate_skipped", msg_id=msg_id)
                    await msg.ack()
                    return

            if parsed.intent == "broadcast":
                admin = await AdminUserRepository(session).get_by_telegram_id(parsed.telegram_id)
                await self._ingest_admin_broadcast_draft(
                    session, admin_id=(admin.id if admin else None), parsed=parsed
                )
                await msg.ack()
                return

            user = await UserRepository(session).get_by_telegram_id(parsed.telegram_id)
            if not user:
                logger.warning("support_msg_user_not_found", telegram_id=parsed.telegram_id)
                if session.has_pending_writes():
                    await session.commit()
                await msg.ack()
                return

            svc = SupportService(
                session,
                nats_client=self._nats,
                outbound_subject=self._config.support_outbound_subject,
            )
            attachments_payload = [
                {
                    "kind": a.kind,
                    "tg_file_id": a.tg_file_id,
                    "tg_file_unique_id": a.tg_file_unique_id,
                    "file_name": a.file_name,
                    "file_size": a.file_size,
                    "mime_type": a.mime_type,
                    "duration": a.duration,
                }
                for a in parsed.attachments
            ]
            ticket, message, is_new_ticket = await svc.ingest_user_message(
                user_id=user.id,
                text=parsed.text,
                attachments_payload=attachments_payload or None,
            )
            if parsed.tg_message_id is not None:
                message.tg_message_id = parsed.tg_message_id
                if session.has_pending_writes():
                    await session.commit()
            logger.info(
                "support_msg_ingested",
                ticket_id=str(ticket.id),
                message_id=str(message.id),
                telegram_id=parsed.telegram_id,
            )

            if is_new_ticket:
                try:
                    await NotificationService(self._nats).publish_support_message(
                        ticket_id=str(ticket.id),
                        telegram_id=parsed.telegram_id,
                        username=getattr(user, "username", None),
                        text=parsed.text or "",
                    )
                except Exception:
                    logger.exception("support_msg_notify_failed", ticket_id=str(ticket.id))
        await msg.ack()

    async def _ingest_admin_broadcast_draft(self, session, *, admin_id, parsed) -> None:
        settings = get_settings()
        entities = parsed.entities or parsed.caption_entities
        custom_emoji_ids = [
            e.custom_emoji_id
            for e in entities
            if e.type == "custom_emoji" and e.custom_emoji_id
        ]
        assets: dict[str, str] = {}
        if custom_emoji_ids:
            assets = await CustomEmojiResolver(
                support=settings.support, s3=settings.s3
            ).resolve(custom_emoji_ids)
        text_html = custom_emoji_entities_to_html(parsed.text or "", entities)
        media_kind: str | None = None
        media_url: str | None = None
        if parsed.attachments:
            att = parsed.attachments[0]
            media_url = await TelegramMediaResolver(
                support=settings.support, s3=settings.s3
            ).resolve(att.tg_file_id)
            if media_url:
                media_kind = att.kind
        svc = SupportService(
            session,
            nats_client=self._nats,
            outbound_subject=self._config.support_outbound_subject,
        )
        broadcast = await svc.create_broadcast(
            audience=BroadcastAudience.ALL,
            plan_id=None,
            text=text_html,
            buttons=None,
            media_kind=media_kind,
            media_url=media_url,
            status=BroadcastStatus.DRAFT,
            scheduled_at=None,
            actor_admin_id=admin_id,
            entities=None,
            custom_emoji_assets=assets or None,
        )
        logger.info(
            "broadcast_draft_from_admin",
            broadcast_id=str(broadcast.id),
            admin_id=str(admin_id),
            emoji_count=len(assets),
            entities_total=len(entities),
            entity_types=[e.type for e in entities],
            cei_present=[bool(e.custom_emoji_id) for e in entities],
            caption_entities_total=len(parsed.caption_entities),
            from_caption=bool(not parsed.entities and parsed.caption_entities),
        )

    @staticmethod
    def _parse_payload(raw_payload: bytes) -> SupportInboundMessage | None:
        try:
            obj = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("support_msg_payload_invalid", error=str(exc))
            return None
        try:
            return SupportInboundMessage.model_validate(obj)
        except ValidationError as exc:
            logger.warning("support_msg_payload_schema_invalid", error=str(exc))
            return None


class SupportSentConsumer:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nats = NatsClient(config)
        self._running = False

    async def start(self):
        if not self._config.enabled:
            logger.info("support_sent_consumer_disabled")
            return

        await self._nats.connect()
        await self._nats.ensure_stream(
            name=self._config.js_support_stream,
            subjects=[
                self._config.support_inbound_subject,
                self._config.support_outbound_subject,
                self._config.support_sent_subject,
            ],
            max_msgs_per_subject=self._config.js_support_max_msgs_per_subject,
            max_age=self._config.js_support_max_age_s,
            duplicate_window=self._config.js_support_duplicate_window_s,
        )
        await self._nats.jetstream_subscribe_durable(
            subject=self._config.support_sent_subject,
            durable=self._config.support_sent_queue,
            queue=self._config.support_sent_queue,
            handler=self._handle_message,
            ack_wait_s=self._config.js_support_ack_wait_s,
            max_deliver=self._config.js_support_max_deliver,
        )
        self._running = True
        logger.info(
            "support_sent_consumer_started",
            subject=self._config.support_sent_subject,
            queue=self._config.support_sent_queue,
        )

    async def stop(self):
        if not self._running:
            return
        await self._nats.close()
        self._running = False
        logger.info("support_sent_consumer_stopped")

    async def _handle_message(self, raw_payload: bytes, msg):
        parsed = self._parse_payload(raw_payload)
        if not parsed:
            await msg.ack()
            return

        msg_id = (msg.headers or {}).get("Nats-Msg-Id") if hasattr(msg, "headers") else None

        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            if msg_id:
                dedup = NatsMessageDedupRepository(session)
                claimed = await dedup.claim(subject=msg.subject, msg_id=msg_id)
                if not claimed:
                    logger.info("support_sent_duplicate_skipped", msg_id=msg_id)
                    await msg.ack()
                    return

            if not parsed.ok:
                logger.warning(
                    "support_sent_ack_failed",
                    message_id=str(parsed.message_id),
                    error=parsed.error or "",
                )
                if session.has_pending_writes():
                    await session.commit()
                await msg.ack()
                return

            updated = await SupportMessageRepository(session).mark_delivered(
                message_id=parsed.message_id,
                tg_message_id=parsed.tg_message_id,
            )
            if updated is None:
                logger.warning(
                    "support_sent_ack_unknown_message",
                    message_id=str(parsed.message_id),
                )
                if session.has_pending_writes():
                    await session.commit()
                await msg.ack()
                return

            await session.commit()
            logger.info(
                "support_msg_delivered",
                message_id=str(parsed.message_id),
                tg_message_id=parsed.tg_message_id,
            )
        await msg.ack()

    @staticmethod
    def _parse_payload(raw_payload: bytes) -> SupportSentAck | None:
        try:
            obj = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("support_sent_payload_invalid", error=str(exc))
            return None
        try:
            return SupportSentAck.model_validate(obj)
        except ValidationError as exc:
            logger.warning("support_sent_payload_schema_invalid", error=str(exc))
            return None


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
        if event is None or event.kind not in DRIP_TRIGGER_EVENTS:
            await msg.ack()
            return
        session_maker = AsyncDatabase.get_session_maker()
        async with session_maker() as session:
            svc = SupportService(
                session,
                nats_client=self._nats,
                outbound_subject=self._config.support_outbound_subject,
            )
            try:
                enrolled = await svc.enroll_drip_for_event(
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
