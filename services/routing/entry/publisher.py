from __future__ import annotations

import logging
from uuid import UUID

from services.config import EntryRoutingConfig, NatsConfig, get_settings
from services.routing.entry.constants import (
    KV_BUCKET,
    KV_KEY_PREFIX,
)
from services.routing.entry.service import EntryRoutingService
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.base import Reconciler
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("entry-routing-publisher"))


class EntryRoutingPublisher(Reconciler):
    name = "entry_routing_publisher"

    def __init__(
        self,
        *,
        routing_config: EntryRoutingConfig | None = None,
        nats_config: NatsConfig | None = None,
        nats_client: NatsClient | None = None,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        settings = get_settings()
        self._cfg = routing_config or settings.entry_routing
        self._nats_cfg = nats_config or settings.nats
        super().__init__(
            interval_sec=max(5, int(self._cfg.publisher_tick_sec)),
            enabled=bool(self._cfg.enabled),
            tick_lock=tick_lock,
        )
        self._session_maker = AsyncDatabase.get_session_maker()
        self._nats: NatsClient | None = nats_client
        self._owns_nats = nats_client is None
        self._last_signatures: dict[UUID, str] = {}

    async def stop(self):
        await super().stop()
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

    async def tick(self):
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
