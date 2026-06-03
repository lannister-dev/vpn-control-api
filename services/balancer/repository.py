from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.balancer.types import KeyLoad, Move, NodeLoad
from services.nodes.models import NodeAgentState, VpnNode
from services.placements.models import UserPlacement
from services.traffic.nodes.repository import NodeTrafficUsageRepository
from services.traffic.users.models import TrafficUsage
from services.vpn.keys.models import VpnKey
from shared.database.base_repository import BaseRepository


class BalancerRepository(BaseRepository[VpnKey]):
    def __init__(self, session: AsyncSession):
        super().__init__(VpnKey, session)

    async def load_nodes(self, *, window_sec: int) -> list[NodeLoad]:
        now = datetime.now(timezone.utc)
        rows = (await self.session.execute(
            select(VpnNode, NodeAgentState)
            .outerjoin(NodeAgentState, NodeAgentState.node_id == VpnNode.id)
            .where(
                VpnNode.role == "backend",
                VpnNode.is_enabled.is_(True),
                VpnNode.is_active.is_(True),
                VpnNode.is_draining.is_(False),
            )
        )).all()
        if not rows:
            return []

        aggregates = await NodeTrafficUsageRepository(self.session).sum_backend_self(
            from_ts=now - timedelta(seconds=window_sec), to_ts=now,
        )
        bytes_by_node = {a.node_id: int(a.bytes_in) + int(a.bytes_out) for a in aggregates}
        sessions_by_node = {a.node_id: int(a.active_sessions) for a in aggregates}

        return [
            NodeLoad(
                node_id=node.id,
                name=node.name,
                bps=bytes_by_node.get(node.id, 0) / max(1, window_sec),
                sessions=sessions_by_node.get(node.id, 0),
                cpu_pct=_cpu_pct(state.details if state else None),
                capacity=float(node.capacity or 100),
            )
            for node, state in rows
        ]

    async def load_keys(
        self, *, window_sec: int, cooldown_sec: int, live_node_ids: set[UUID],
        node_name_by_id: dict[UUID, str],
    ) -> list[KeyLoad]:
        now = datetime.now(timezone.utc)
        cooldown_cut = now - timedelta(seconds=cooldown_sec)

        key_rows = (await self.session.execute(
            select(VpnKey.id, VpnKey.entry_routing_override_backend_tag)
            .where(
                VpnKey.is_active.is_(True),
                VpnKey.valid_until > now,
                or_(VpnKey.is_revoked.is_(False), VpnKey.is_revoked.is_(None)),
                VpnKey.updated_at < cooldown_cut,
            )
        )).all()
        if not key_rows:
            return []
        key_ids = [r[0] for r in key_rows]
        override_by_key = {r[0]: r[1] for r in key_rows}

        placements = (await self.session.execute(
            select(UserPlacement.key_id, UserPlacement.backend_node_id, UserPlacement.op_version)
            .where(
                UserPlacement.key_id.in_(key_ids),
                UserPlacement.desired_state == "active",
                UserPlacement.is_active.is_(True),
            )
        )).all()

        traffic = (await self.session.execute(
            select(TrafficUsage.key_id, func.coalesce(func.sum(TrafficUsage.delta_bytes), 0))
            .where(
                TrafficUsage.key_id.in_(key_ids),
                TrafficUsage.created_at >= now - timedelta(seconds=window_sec),
                TrafficUsage.created_at < now,
            )
            .group_by(TrafficUsage.key_id)
        )).all()
        bps_by_key = {r[0]: int(r[1]) / max(1, window_sec) for r in traffic}

        eligible: dict[UUID, set[UUID]] = {}
        primary: dict[UUID, tuple[int, UUID]] = {}
        for kid, bid, opv in placements:
            if bid not in live_node_ids:
                continue
            eligible.setdefault(kid, set()).add(bid)
            if kid not in primary or opv > primary[kid][0]:
                primary[kid] = (opv, bid)

        tag_to_id = {f"backend-{name}": nid for nid, name in node_name_by_id.items()}
        out: list[KeyLoad] = []
        for kid in key_ids:
            elig = eligible.get(kid)
            if not elig:
                continue
            tag = override_by_key.get(kid)
            current = tag_to_id.get(tag) if tag in tag_to_id else None
            if current not in elig:
                current = primary[kid][1] if kid in primary else None
            out.append(KeyLoad(
                key_id=kid,
                bps=bps_by_key.get(kid, 0.0),
                current_backend_id=current,
                eligible_backend_ids=frozenset(elig),
            ))
        return out

    async def apply_moves(self, moves: list[Move]) -> int:
        if not moves:
            return 0
        for m in moves:
            await self.update_by_id(m.key_id, {"entry_routing_override_backend_tag": m.to_tag})
        await self.session.commit()
        return len(moves)


def _cpu_pct(details: dict | None) -> float:
    try:
        return float((details or {}).get("stats", {}).get("cpu_pct", 0.0))
    except (TypeError, ValueError, AttributeError):
        return 0.0
