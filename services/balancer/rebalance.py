from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.balancer.scoring import (
    BackendStat,
    KeyStat,
    Weights,
    plan_moves,
)
from services.config import get_settings
from services.nodes.models import NodeAgentState
from services.nodes.repository import VpnNodeRepository
from services.placements.repository import UserPlacementRepository
from services.placements.schemas import PlacementDesiredState
from services.placements.transport import NodeAgentPlacementTransport
from services.traffic.nodes.models import NodeTrafficUsage
from services.traffic.users.models import TrafficUsage
from services.vpn.keys.repository import VpnKeyRepository
from services.vpn.keys.schemas import VpnKeyRoutingOverrideUpdate
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("balancer.rebalance"))


class BackendRebalancer:
    def __init__(self, session: AsyncSession, *, nats=None) -> None:
        self._session = session
        self._nats = nats
        self._node_repository = VpnNodeRepository(session)
        self._key_repository = VpnKeyRepository(session)
        self._placement_repository = UserPlacementRepository(session)
        self._transport = NodeAgentPlacementTransport(session)
        self._cfg = get_settings().backend_rebalance

    async def rebalance(self) -> int:
        backends = await self._node_repository.list_live_backends()
        if len(backends) < 2:
            return 0
        nodes_by_id = {b.id: b for b in backends}
        tag_by_id = {b.id: f"backend-{b.name}" for b in backends}
        live_tags = set(tag_by_id.values())

        keys = await self._key_repository.list_all_active()
        if not keys:
            return 0

        eligible = await self._placement_repository.map_active_backend_nodes_by_key(
            key_ids=[k.id for k in keys],
        )

        since = datetime.now(timezone.utc) - timedelta(minutes=self._cfg.traffic_window_min)
        key_bytes = await self._recent_bytes_by_key(since)
        cpu_by_tag = await self._cpu_by_backend(nodes_by_id)
        selected = await self._placement_repository.map_selected_backend_by_key(
            key_ids=[k.id for k in keys],
        )

        conn_by_tag = dict.fromkeys(live_tags, 0)
        bytes_by_tag = dict.fromkeys(live_tags, 0.0)
        key_stats: list[KeyStat] = []
        for k in keys:
            allowed = frozenset(
                tag_by_id[bid] for bid in eligible.get(k.id, set()) if bid in tag_by_id
            )
            if not allowed:
                continue
            cur = k.entry_routing_override_backend_tag
            if cur not in live_tags:
                sel = selected.get(k.id)
                cur = tag_by_id.get(sel) if sel else None
            if cur not in live_tags:
                continue
            w = float(key_bytes.get(k.id, 0))
            key_stats.append(KeyStat(key_id=k.id, current_tag=cur, allowed_tags=allowed, weight=w))
            conn_by_tag[cur] += 1
            bytes_by_tag[cur] += w

        backend_stats = [
            BackendStat(
                tag=tag,
                recent_bytes=bytes_by_tag.get(tag, 0.0),
                cpu_pct=cpu_by_tag.get(tag, 0.0),
                conn=conn_by_tag.get(tag, 0),
                capacity=max(1, int(getattr(nodes_by_id[bid], "capacity", 100) or 100)),
            )
            for bid, tag in tag_by_id.items()
        ]

        moves = plan_moves(
            backend_stats,
            key_stats,
            weights=Weights(
                bandwidth=self._cfg.weight_bandwidth,
                cpu=self._cfg.weight_cpu,
                conn=self._cfg.weight_conn,
            ),
            spread_threshold=self._cfg.score_spread_threshold,
            move_cap=self._cfg.move_cap,
        )
        if not moves:
            return 0

        for m in moves:
            await self._apply_move(m.key_id, m.to_tag)

        logger.info(
            "backend_rebalance_applied",
            moved=len(moves),
            backends=len(backends),
            loads={s.tag: round(s.recent_bytes / 1048576.0, 1) for s in backend_stats},
        )
        return len(moves)

    async def _recent_bytes_by_key(self, since: datetime) -> dict:
        res = await self._session.execute(
            select(TrafficUsage.key_id, func.sum(TrafficUsage.delta_bytes))
            .where(TrafficUsage.created_at >= since)
            .group_by(TrafficUsage.key_id)
        )
        return {row[0]: int(row[1] or 0) for row in res.all()}

    async def _recent_bytes_by_backend(self, nodes_by_id: dict, since: datetime) -> dict:
        if not nodes_by_id:
            return {}
        res = await self._session.execute(
            select(
                NodeTrafficUsage.backend_node_id,
                func.sum(NodeTrafficUsage.bytes_in + NodeTrafficUsage.bytes_out),
            )
            .where(
                NodeTrafficUsage.created_at >= since,
                NodeTrafficUsage.backend_node_id.in_(list(nodes_by_id.keys())),
            )
            .group_by(NodeTrafficUsage.backend_node_id)
        )
        out: dict[str, float] = {}
        for node_id, total in res.all():
            node = nodes_by_id.get(node_id)
            if node is not None:
                out[f"backend-{node.name}"] = float(total or 0)
        return out

    async def _cpu_by_backend(self, nodes_by_id: dict) -> dict:
        if not nodes_by_id:
            return {}
        res = await self._session.execute(
            select(NodeAgentState.node_id, NodeAgentState.details)
            .where(NodeAgentState.node_id.in_(list(nodes_by_id.keys())))
        )
        out: dict[str, float] = {}
        for node_id, details in res.all():
            cpu = 0.0
            if isinstance(details, dict):
                stats = details.get("stats")
                if isinstance(stats, dict):
                    raw = stats.get("cpu_pct")
                    if isinstance(raw, (int, float)):
                        cpu = float(raw)
            node = nodes_by_id.get(node_id)
            if node is not None:
                out[f"backend-{node.name}"] = cpu
        return out

    async def _apply_move(self, key_id, to_tag: str) -> None:
        await self._key_repository.update_by_id(
            key_id,
            VpnKeyRoutingOverrideUpdate(
                entry_routing_override_backend_tag=to_tag,
            ).model_dump(exclude_unset=True),
        )
        await self._transport.enqueue_for_key_state(
            key_id=key_id,
            desired_state=PlacementDesiredState.active.value,
        )
