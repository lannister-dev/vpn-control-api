from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

try:
    import nats
    from nats.errors import NoServersError
except ModuleNotFoundError:  # pragma: no cover
    nats = None
    NoServersError = Exception

from services.config import NatsConfig
from shared.utils.logger import StructuredLogger


logger_nats = StructuredLogger(logging.getLogger("nats-client"))


class NatsClient:
    def __init__(self, config: NatsConfig):
        self._config = config
        self._nc: nats.aio.client.Client | None = None
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

    async def close(self) -> None:
        if self._nc and not self._nc.is_closed:
            await self._nc.drain()
            await self._nc.close()
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
