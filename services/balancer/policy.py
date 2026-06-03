from __future__ import annotations

from uuid import UUID

from services.balancer.constants import EPS
from services.balancer.types import BalancePlan, KeyLoad, Move, NodeLoad
from services.config import BalancerConfig


class BalancerPolicy:
    def __init__(self, config: BalancerConfig):
        self._cfg = config

    def plan(self, nodes: list[NodeLoad], keys: list[KeyLoad]) -> BalancePlan:
        cfg = self._cfg
        if len(nodes) < 2:
            return BalancePlan(skipped_reason="need_two_nodes")

        by_id = {n.node_id: n for n in nodes}
        total_cap = sum(max(0.0, n.capacity) for n in nodes) or float(len(nodes))
        total_sess = float(sum(max(0, n.sessions) for n in nodes))
        wsum = (cfg.w_throughput + cfg.w_sessions) or 1.0

        bps = {n.node_id: max(0.0, n.bps) for n in nodes}
        cap = {n.node_id: (max(0.0, n.capacity) or 1.0) for n in nodes}
        sess = {n.node_id: float(max(0, n.sessions)) for n in nodes}

        def target_share(nid: UUID) -> float:
            return cap[nid] / total_cap

        def actual_share(nid: UUID) -> float:
            total_bps = sum(bps.values())
            bps_share = bps[nid] / total_bps if total_bps > EPS else target_share(nid)
            sess_share = sess[nid] / total_sess if total_sess > EPS else target_share(nid)
            return (cfg.w_throughput * bps_share + cfg.w_sessions * sess_share) / wsum

        def deviation(nid: UUID) -> float:
            return actual_share(nid) - target_share(nid)

        def is_full(nid: UUID) -> bool:
            return by_id[nid].cpu_pct >= cfg.cpu_full_pct

        keys_on = self._group_keys_by_node(keys, set(by_id))
        used: set[UUID] = set()
        moves: list[Move] = []

        while len(moves) < cfg.max_moves_per_tick:
            srcs = sorted(
                (n for n in nodes if any(k.key_id not in used for k in keys_on.get(n.node_id, []))),
                key=lambda n: deviation(n.node_id),
                reverse=True,
            )
            sinks = sorted(
                (n for n in nodes if not is_full(n.node_id)),
                key=lambda n: deviation(n.node_id),
            )
            picked: list[KeyLoad] = []
            chosen_src = chosen_sink = None
            for src in srcs:
                if not sinks or deviation(src.node_id) - deviation(sinks[0].node_id) <= cfg.dead_zone:
                    break
                for sink in sinks:
                    if sink.node_id == src.node_id:
                        continue
                    if deviation(src.node_id) - deviation(sink.node_id) <= cfg.dead_zone:
                        break
                    need = self._move_need(bps, target_share, src.node_id, sink.node_id)
                    cand = self._select_keys(keys_on[src.node_id], used, sink.node_id, need)
                    if cand:
                        picked, chosen_src, chosen_sink = cand, src, sink
                        break
                if picked:
                    break
            if not picked or chosen_src is None or chosen_sink is None:
                break

            moved_bps = sum(k.bps for k in picked)
            for k in picked:
                used.add(k.key_id)
                moves.append(Move(
                    key_id=k.key_id,
                    from_backend_id=chosen_src.node_id,
                    to_backend_id=chosen_sink.node_id,
                    to_tag=f"backend-{chosen_sink.name}",
                    bps=k.bps,
                ))
                if len(moves) >= cfg.max_moves_per_tick:
                    break
            bps[chosen_src.node_id] = max(0.0, bps[chosen_src.node_id] - moved_bps)
            bps[chosen_sink.node_id] += moved_bps
            sess[chosen_src.node_id] = max(0.0, sess[chosen_src.node_id] - len(picked))
            sess[chosen_sink.node_id] += len(picked)

        return BalancePlan(
            moves=moves,
            deviations={n.node_id: round(deviation(n.node_id), 4) for n in nodes},
        )

    @staticmethod
    def _group_keys_by_node(keys: list[KeyLoad], known: set[UUID]) -> dict[UUID, list[KeyLoad]]:
        grouped: dict[UUID, list[KeyLoad]] = {}
        for k in keys:
            if k.current_backend_id in known:
                grouped.setdefault(k.current_backend_id, []).append(k)
        for lst in grouped.values():
            lst.sort(key=lambda k: k.bps, reverse=True)
        return grouped

    def _move_need(self, bps, target_share, src_id, sink_id) -> float:
        total_bps = sum(bps.values())
        excess = bps[src_id] - target_share(src_id) * total_bps
        deficit = target_share(sink_id) * total_bps - bps[sink_id]
        return self._cfg.move_fraction * max(0.0, min(excess, deficit))

    @staticmethod
    def _select_keys(src_keys, used, sink_id, need) -> list[KeyLoad]:
        eligible = [
            k for k in src_keys
            if k.key_id not in used and sink_id in k.eligible_backend_ids
        ]
        if not eligible:
            return []
        if need <= EPS:
            return [min(eligible, key=lambda k: k.bps)]
        picked: list[KeyLoad] = []
        remaining = need
        for k in eligible:
            if k.bps <= remaining + EPS:
                picked.append(k)
                remaining -= k.bps
        if not picked:
            picked = [min(eligible, key=lambda k: k.bps)]
        return picked
