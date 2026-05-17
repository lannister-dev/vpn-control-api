from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from uuid import UUID

from services.config import EntryRoutingConfig, NatsConfig, get_settings
from services.nodes.repository import VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.routing.entry.constants import KV_STATS_BUCKET
from services.vpn.keys.models import VpnKey
from services.vpn.keys.repository import VpnKeyRepository
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("backend-rebalance-reconciler"))


class BackendRebalanceReconciler:
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
        self._enabled = bool(self._cfg.enabled)
        self._interval_sec = max(30, int(self._cfg.backend_rebalance_tick_sec))
        self._session_maker = AsyncDatabase.get_session_maker()
        self._nats: NatsClient | None = nats_client
        self._owns_nats = nats_client is None
        self._tick_lock = tick_lock or RedisTickLock(
            key="reconciler:backend_rebalance",
            ttl_sec=max(60, self._interval_sec * 2),
            fail_open_if_client_unavailable=True,
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        if not self._enabled:
            logger.info("backend_rebalance_disabled")
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        if self._owns_nats and self._nats is not None:
            await self._nats.close()
            self._nats = None

    async def run_once(self) -> int | None:
        if not self._enabled:
            return None
        async with self._tick_lock.hold() as acquired:
            if not acquired:
                return None
            return await self._tick()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._enabled:
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("backend_rebalance_tick_failed")
            watchdog.heartbeat(self.__class__.__name__, max_silence_sec=self._interval_sec * 2 + 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _ensure_nats(self) -> NatsClient:
        if self._nats is None:
            self._nats = NatsClient(self._nats_cfg)
        if not self._nats.is_connected:
            await self._nats.connect()
        return self._nats

    async def _fetch_backend_loads(self, nats: NatsClient) -> dict[str, int]:
        out: dict[str, int] = {}
        try:
            entries = await nats.kv_list_all(bucket=KV_STATS_BUCKET)
        except Exception:
            logger.exception("backend_rebalance_kv_read_failed")
            return out
        for raw in entries.values():
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            for tag, count in (payload.get("by_backend") or {}).items():
                out[tag] = out.get(tag, 0) + int(count)
        return out

    async def _tick(self) -> int:
        nats = await self._ensure_nats()
        backend_loads = await self._fetch_backend_loads(nats)
        async with self._session_maker() as session:
            key_repo = VpnKeyRepository(session)
            placement_repo = UserPlacementRepository(session)
            node_repo = VpnNodeRepository(session)

            keys = await key_repo.list_all_active()
            if not keys:
                return 0
            live_backends = await node_repo.list_live_backends()
            nodes_by_id = {n.id: n for n in live_backends}
            if not nodes_by_id:
                return 0

            allowed_by_key = await placement_repo.map_active_backend_nodes_by_key(
                key_ids=[k.id for k in keys],
            )

            changed = 0
            for key in keys:
                allowed = allowed_by_key.get(key.id)
                if not allowed:
                    continue
                chosen_tag = self._pick_least_loaded(
                    key=key,
                    allowed=allowed,
                    nodes_by_id=nodes_by_id,
                    backend_loads=backend_loads,
                )
                if chosen_tag is None:
                    continue
                if key.entry_routing_override_backend_tag != chosen_tag:
                    await key_repo.update_by_id(
                        key.id,
                        {"entry_routing_override_backend_tag": chosen_tag},
                    )
                    changed += 1
                    backend_loads[chosen_tag] = backend_loads.get(chosen_tag, 0) + 1
            await session.commit()
            if changed:
                logger.info("backend_rebalance_applied", changed=changed, total=len(keys))
            return changed

    @staticmethod
    def _pick_least_loaded(
        *,
        key: VpnKey,
        allowed: set[UUID],
        nodes_by_id: dict[UUID, object],
        backend_loads: dict[str, int],
    ) -> str | None:
        candidates: list[tuple[int, int, str]] = []
        for bid in allowed:
            node = nodes_by_id.get(bid)
            if node is None:
                continue
            tag = f"backend-{node.name}"
            load = int(backend_loads.get(tag, 0))
            tiebreak = int.from_bytes(
                hashlib.sha256(f"{key.id}:{bid}".encode()).digest()[:8],
                "big",
            )
            candidates.append((load, tiebreak, tag))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]
