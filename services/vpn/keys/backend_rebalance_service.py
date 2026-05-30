from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.config import EntryRoutingConfig, get_settings
from services.nodes.repository import VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.traffic.nodes.repository import NodeTrafficUsageRepository
from services.vpn.keys.repository import VpnKeyRepository
from shared.database.session import AsyncDatabase
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("backend-rebalance"))


class BackendRebalanceService:
    def __init__(self, *, routing_config: EntryRoutingConfig | None = None) -> None:
        settings = get_settings()
        self._cfg = routing_config or settings.entry_routing
        self._enabled = bool(self._cfg.backend_rebalance_enabled)
        self._window_sec = max(60, int(self._cfg.backend_rebalance_window_sec))
        self._ratio_threshold = float(self._cfg.backend_rebalance_ratio_threshold)
        self._min_bytes_per_sec = int(self._cfg.backend_rebalance_min_bytes_per_sec)
        self._cooldown_sec = int(self._cfg.backend_rebalance_cooldown_sec)
        self._batch_size = max(1, int(self._cfg.backend_rebalance_batch_size))
        self._session_maker = AsyncDatabase.get_session_maker()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def run_once(self) -> int:
        if not self._enabled:
            return 0
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
            aggregates = await traffic_repo.sum_backend_self(from_ts=window_from, to_ts=now)
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
                order_by_traffic_desc=True,
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
        out: dict[UUID, int] = dict.fromkeys(nodes_by_id, 0)
        for agg in aggregates:
            if agg.node_id not in nodes_by_id:
                continue
            total = int(agg.bytes_in) + int(agg.bytes_out)
            out[agg.node_id] = total // max(1, self._window_sec)
        return out
