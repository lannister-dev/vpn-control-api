from __future__ import annotations
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
import json
import nats
from nats.errors import (
    ConnectionClosedError,
    NoServersError,
    OutboundBufferLimitError,
    TimeoutError as NatsTimeoutError,
)
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, StreamConfig

from services.config import NatsConfig
from shared.utils.logger import StructuredLogger


logger_nats = StructuredLogger(logging.getLogger("nats-client"))


class NatsClient:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nc: nats.aio.client.Client | None = None
        self._js = None
        self._connected = False
        self._disconnected_since: float | None = None
        self._reconnecting = False
        self._reconnect_callbacks: list[Callable[[], Awaitable[None]]] = []

    @property
    def is_connected(self) -> bool:
        return self._connected and self._nc is not None and not self._nc.is_closed

    def on_reconnect(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._reconnect_callbacks.append(callback)

    async def connect(self) -> None:
        try:
            self._nc = await nats.connect(
                servers=self._config.server,
                name=self._config.name,
                reconnect_time_wait=self._config.reconnect_time_wait,
                max_reconnect_attempts=self._config.max_reconnect_attempts,
                disconnected_cb=self._on_disconnected,
                reconnected_cb=self._on_reconnected,
                error_cb=self._on_error,
                closed_cb=self._on_closed,
                ping_interval=20,
                max_outstanding_pings=3,
                pending_size=8 * 1024 * 1024,
                flusher_queue_size=512,
            )
            self._connected = True
            self._disconnected_since = None
            self._js = self._nc.jetstream()
            logger_nats.info("nats_connected", server=self._config.server)
        except NoServersError as exc:
            self._connected = False
            logger_nats.error("nats_connect_failed", error=str(exc))
            raise

    async def close(self) -> None:
        if self._nc and not self._nc.is_closed:
            try:
                await self._nc.drain()
            except Exception:
                pass
            try:
                await self._nc.close()
            except Exception:
                pass
        self._nc = None
        self._js = None
        self._connected = False

    async def force_reconnect(self) -> None:
        """Tear down and re-establish the NATS connection.

        Handles scenarios where nats-py built-in reconnect cannot recover
        (e.g. Docker overlay network partition, permanently closed state).
        """
        if self._reconnecting:
            return
        self._reconnecting = True
        try:
            logger_nats.warning("nats_force_reconnect_start")
            await self.close()
            await self.connect()
            logger_nats.info("nats_force_reconnect_success")
            for cb in self._reconnect_callbacks:
                try:
                    await cb()
                except Exception:
                    logger_nats.exception("reconnect_callback_failed")
        finally:
            self._reconnecting = False

    async def ensure_connected(self) -> None:
        """Check health and force-reconnect if disconnected too long."""
        if self.is_connected:
            self._disconnected_since = None
            return
        now = time.monotonic()
        if self._disconnected_since is None:
            self._disconnected_since = now
            return
        elapsed = now - self._disconnected_since
        if elapsed >= self._config.force_reconnect_after_s:
            logger_nats.warning(
                "nats_disconnected_too_long",
                elapsed_s=round(elapsed, 1),
            )
            try:
                await self.force_reconnect()
            except Exception:
                logger_nats.exception("nats_force_reconnect_failed")

    async def subscribe(
            self,
            *,
            subject: str,
            handler: Callable[[bytes], Awaitable[None]],
            queue: str | None = None,
    ) -> None:
        if not self._nc or not self._connected:
            raise RuntimeError("NATS is not connected")

        async def _wrapper(msg):
            try:
                await handler(msg.data)
            except Exception:
                logger_nats.exception("nats_subscriber_handler_failed", subject=subject)

        await self._nc.subscribe(subject=subject, queue=queue, cb=_wrapper)
        logger_nats.info("nats_subscribed", subject=subject, queue=queue)

    def jetstream(self):
        if not self._js:
            raise RuntimeError("NATS JetStream is not connected")
        return self._js

    async def publish_jetstream(
        self,
        *,
        subject: str,
        payload: dict | bytes,
        msg_id: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        await self.ensure_connected()
        if not self.is_connected:
            raise RuntimeError("NATS is not connected")

        if isinstance(payload, dict):
            payload = json.dumps(payload).encode()
        message_headers = dict(headers or {})
        if msg_id:
            message_headers["Nats-Msg-Id"] = msg_id

        try:
            return await self.jetstream().publish(
                subject,
                payload,
                headers=message_headers or None,
            )
        except OutboundBufferLimitError:
            logger_nats.warning("nats_outbound_buffer_full_flush")
            try:
                await asyncio.wait_for(self._nc.flush(), timeout=5.0)
                return await self.jetstream().publish(
                    subject,
                    payload,
                    headers=message_headers or None,
                )
            except Exception as e:
                logger_nats.error("nats_publish_after_flush_failed", error=str(e))
                raise
        except (ConnectionClosedError, NatsTimeoutError) as e:
            logger_nats.error("nats_publish_jetstream_failed", error=str(e))
            raise

    async def ensure_stream(
        self,
        *,
        name: str,
        subjects: list[str],
        max_msgs_per_subject: int = 1000,
        max_age: float = 3600,
    ):
        config = StreamConfig(
            name=name,
            subjects=subjects,
            max_msgs_per_subject=max_msgs_per_subject,
            max_age=max_age,
        )
        try:
            info = await self.jetstream().stream_info(name)
        except Exception:
            return await self.jetstream().add_stream(config=config)
        current_subjects = set(info.config.subjects or [])
        desired_subjects = current_subjects | set(subjects)
        needs_update = desired_subjects != current_subjects
        if info.config.max_msgs_per_subject != max_msgs_per_subject:
            needs_update = True
        if info.config.max_age != max_age:
            needs_update = True
        if not needs_update:
            return info
        info.config.subjects = sorted(desired_subjects)
        info.config.max_msgs_per_subject = max_msgs_per_subject
        info.config.max_age = max_age
        return await self.jetstream().update_stream(config=info.config)

    async def pull_subscribe(
        self,
        *,
        subject: str,
        durable: str,
        ack_wait_s: float,
        max_deliver: int,
        deliver_policy=DeliverPolicy.ALL,
    ):
        config = ConsumerConfig(
            durable_name=durable,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=ack_wait_s,
            max_deliver=max_deliver,
            deliver_policy=deliver_policy,
        )
        return await self.jetstream().pull_subscribe(
            subject,
            durable=durable,
            config=config,
        )

    async def fetch_messages(self, subscription, *, batch: int, timeout: float):
        return await subscription.fetch(batch=batch, timeout=timeout)

    async def _on_disconnected(self) -> None:
        self._connected = False
        if self._disconnected_since is None:
            self._disconnected_since = time.monotonic()
        logger_nats.warning("nats_disconnected")

    async def _on_reconnected(self) -> None:
        self._connected = True
        self._disconnected_since = None
        self._js = self._nc.jetstream()
        logger_nats.info("nats_reconnected")
        for cb in self._reconnect_callbacks:
            try:
                await cb()
            except Exception:
                logger_nats.exception("reconnect_callback_failed")

    async def _on_error(self, error: Exception) -> None:
        logger_nats.error("nats_error", error=str(error), error_type=type(error).__name__)

    async def _on_closed(self) -> None:
        self._connected = False
        if self._disconnected_since is None:
            self._disconnected_since = time.monotonic()
        logger_nats.warning("nats_closed")
