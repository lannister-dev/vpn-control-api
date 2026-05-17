from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.config import EntryRoutingConfig, get_settings
from services.nodes.repository import VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.traffic.nodes.repository import NodeTrafficUsageRepository
from services.vpn.keys.repository import VpnKeyRepository
from shared.database.session import AsyncDatabase
from shared.reconciler.watchdog import watchdog
from shared.redis.lock import RedisTickLock
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("backend-rebalance-reconciler"))


class BackendRebalanceReconciler:
    def __init__(
        self,
        *,
        routing_config: EntryRoutingConfig | None = None,
        tick_lock: RedisTickLock | None = None,
    ) -> None:
        settings = get_settings()
        self._cfg = routing_config or settings.entry_routing
        self._enabled = bool(self._cfg.backend_rebalance_enabled)
        self._interval_sec = max(60, int(self._cfg.backend_rebalance_tick_sec))
        self._window_sec = max(60, int(self._cfg.backend_rebalance_window_sec))
        self._ratio_threshold = float(self._cfg.backend_rebalance_ratio_threshold)
        self._min_bytes_per_sec = int(self._cfg.backend_rebalance_min_bytes_per_sec)
        self._cooldown_sec = int(self._cfg.backend_rebalance_cooldown_sec)
        self._batch_size = max(1, int(self._cfg.backend_rebalance_batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()
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

    async def _tick(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._session_maker() as session:
            node_repo = VpnNodeRepository(session)
            key_repo = VpnKeyRepository(session)
            placement_repo = UserPlacementRepository(session)
            traffic_repo = NodeTrafficUsageRepository(session)

            live_backends = await node_repo.list_live_backends()
            if len(live_backends) < 2:
                return 0
            nodes_by_id = {n.id: n for n in live_backends}

            window_from = now - timedelta(seconds=self._window_sec)
            aggregates = await traffic_repo.sum_backend_self(
                from_ts=window_from, to_ts=now,
            )
            bps_by_backend = self._compute_bps(aggregates, nodes_by_id)
            if len(bps_by_backend) < 2:
                return 0

            src_id, src_bps = max(bps_by_backend.items(), key=lambda x: x[1])
            dst_id, dst_bps = min(bps_by_backend.items(), key=lambda x: x[1])
            if src_id == dst_id:
                return 0
            if src_bps < self._min_bytes_per_sec:
                return 0
            ratio = src_bps / max(1, dst_bps)
            if ratio < self._ratio_threshold:
                return 0

            src_tag = f"backend-{nodes_by_id[src_id].name}"
            dst_tag = f"backend-{nodes_by_id[dst_id].name}"
            cooldown_at = now - timedelta(seconds=self._cooldown_sec)
            candidates = await key_repo.list_active_by_override_tag(
                tag=src_tag,
                updated_before=cooldown_at,
                limit=self._batch_size * 4,
            )
            if not candidates:
                return 0

            allowed_by_key = await placement_repo.map_active_backend_nodes_by_key(
                key_ids=[k.id for k in candidates],
            )
            moved = 0
            for key in candidates:
                if moved >= self._batch_size:
                    break
                allowed = allowed_by_key.get(key.id)
                if not allowed or dst_id not in allowed:
                    continue
                await key_repo.update_by_id(
                    key.id, {"entry_routing_override_backend_tag": dst_tag},
                )
                moved += 1

            if moved:
                await session.commit()
                logger.info(
                    "backend_rebalance_applied",
                    moved=moved,
                    src=nodes_by_id[src_id].name,
                    dst=nodes_by_id[dst_id].name,
                    src_mbps=round(src_bps * 8 / 1_000_000, 2),
                    dst_mbps=round(dst_bps * 8 / 1_000_000, 2),
                    ratio=round(ratio, 1),
                )
            return moved

    def _compute_bps(
        self,
        aggregates,
        nodes_by_id: dict[UUID, object],
    ) -> dict[UUID, int]:
        out: dict[UUID, int] = {}
        for n in nodes_by_id:
            out[n] = 0
        for agg in aggregates:
            if agg.node_id not in nodes_by_id:
                continue
            total = int(agg.bytes_in) + int(agg.bytes_out)
            out[agg.node_id] = total // max(1, self._window_sec)
        return out
