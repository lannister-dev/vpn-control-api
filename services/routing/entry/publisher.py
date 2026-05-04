from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from services.config import EntryRoutingConfig, NatsConfig, get_settings
from services.routing.entry.constants import (
    KV_BUCKET,
    KV_KEY_PREFIX,
    PUBLISHER_IDLE_WHEN_DISABLED_SEC,
)
from services.routing.entry.service import EntryRoutingService
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.watchdog import watchdog
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("entry-routing-publisher"))


class EntryRoutingPublisher:
    def __init__(
        self,
        *,
        routing_config: EntryRoutingConfig | None = None,
        nats_config: NatsConfig | None = None,
        nats_client: NatsClient | None = None,
    ) -> None:
        settings = get_settings()
        self._cfg = routing_config or settings.entry_routing
        self._nats_cfg = nats_config or settings.nats
        self._enabled = bool(self._cfg.enabled)
        self._interval_sec = max(5, int(self._cfg.publisher_tick_sec))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._nats: NatsClient | None = nats_client
        self._owns_nats = nats_client is None
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._last_signatures: dict[UUID, str] = {}

    async def start(self):
        if self._task is not None and not self._task.done():
            return
        if not self._enabled:
            logger.info("entry_routing_publisher_disabled")
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        if self._owns_nats and self._nats is not None:
            await self._nats.close()
            self._nats = None

    async def _ensure_nats(self) -> NatsClient:
        if self._nats is None:
            self._nats = NatsClient(self._nats_cfg)
        if not self._nats.is_connected:
            await self._nats.connect()
            await self._nats.ensure_kv_bucket(name=KV_BUCKET, history=1)
        return self._nats

    async def _run(self):
        while not self._stop_event.is_set():
            sleep_sec = PUBLISHER_IDLE_WHEN_DISABLED_SEC
            if self._enabled:
                sleep_sec = self._interval_sec
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("entry_routing_publish_tick_failed")

            watchdog.heartbeat(
                self.__class__.__name__,
                max_silence_sec=sleep_sec * 2 + 60,
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_sec)
            except asyncio.TimeoutError:
                continue

    async def _tick(self):
        nats = await self._ensure_nats()
        async with self._session_maker() as session:
            service = EntryRoutingService(session, config=self._cfg)
            target_nodes = await service.list_target_nodes()
            published = 0
            for node in target_nodes:
                spec = await service.build_spec_for_node(node.id)
                if spec is None:
                    continue
                signature = spec.signature()
                if self._last_signatures.get(node.id) == signature:
                    continue
                key = f"{KV_KEY_PREFIX}{node.id}"
                await nats.kv_put(
                    bucket=KV_BUCKET,
                    key=key,
                    payload=spec.model_dump(mode="json"),
                )
                self._last_signatures[node.id] = signature
                published += 1
            if published:
                logger.info(
                    "entry_routing_published",
                    nodes=published,
                    total=len(target_nodes),
                )
