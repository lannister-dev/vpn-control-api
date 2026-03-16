from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
import json

try:
    import nats
    from nats.errors import NoServersError
    from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, StreamConfig
except ModuleNotFoundError:  # pragma: no cover
    nats = None
    NoServersError = Exception
    AckPolicy = ConsumerConfig = DeliverPolicy = StreamConfig = object

from services.config import NatsConfig
from shared.utils.logger import StructuredLogger


logger_nats = StructuredLogger(logging.getLogger("nats-client"))


class NatsClient:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nc: nats.aio.client.Client | None = None
        self._js = None
        self._connected = False

    async def connect(self) -> None:
        if nats is None:
            raise RuntimeError(
                "nats-py is not installed. Install dependencies or disable NATS integration."
            )
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
            )
            self._connected = True
            self._js = self._nc.jetstream()
            logger_nats.info("nats_connected", server=self._config.server)
        except NoServersError as exc:
            self._connected = False
            logger_nats.error("nats_connect_failed", error=str(exc))
            raise

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
        if isinstance(payload, dict):
            payload = json.dumps(payload).encode()
        message_headers = dict(headers or {})
        if msg_id:
            message_headers["Nats-Msg-Id"] = msg_id
        return await self.jetstream().publish(
            subject,
            payload,
            headers=message_headers or None,
        )

    async def ensure_stream(
        self,
        *,
        name: str,
        subjects: list[str],
    ):
        config = StreamConfig(name=name, subjects=subjects)
        try:
            info = await self.jetstream().stream_info(name)
        except Exception:
            return await self.jetstream().add_stream(config=config)
        current_subjects = set(info.config.subjects or [])
        desired_subjects = current_subjects | set(subjects)
        if desired_subjects == current_subjects:
            return info
        info.config.subjects = sorted(desired_subjects)
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

    async def close(self) -> None:
        if self._nc and not self._nc.is_closed:
            await self._nc.drain()
            await self._nc.close()
        self._js = None
        self._connected = False

    async def _on_disconnected(self) -> None:
        self._connected = False
        logger_nats.warning("nats_disconnected")

    async def _on_reconnected(self) -> None:
        self._connected = True
        logger_nats.info("nats_reconnected")

    async def _on_error(self, error: Exception) -> None:
        logger_nats.error("nats_error", error=str(error))

    async def _on_closed(self) -> None:
        self._connected = False
        logger_nats.warning("nats_closed")
