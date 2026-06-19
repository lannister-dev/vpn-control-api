from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendStat:
    tag: str
    recent_bytes: float
    cpu_pct: float
    conn: int
    capacity: int


@dataclass(frozen=True)
class KeyStat:
    key_id: object
    current_tag: str
    allowed_tags: frozenset[str]
    weight: float


@dataclass(frozen=True)
class Move:
    key_id: object
    from_tag: str
    to_tag: str


@dataclass(frozen=True)
class Weights:
    bandwidth: float = 0.5
    cpu: float = 0.3
    conn: float = 0.2


@dataclass
class _Working:
    tag: str
    bytes: float
    cpu: float
    conn: int
    cap: int

    @property
    def bw_load(self) -> float:
        return self.bytes / max(1, self.cap)

    @property
    def cpu_load(self) -> float:
        return (self.cpu or 0.0) / 100.0

    @property
    def conn_load(self) -> float:
        return self.conn / max(1, self.cap)


def _relative_to_mean(raw: dict[str, float]) -> dict[str, float]:
    if not raw:
        return {}
    mean = sum(raw.values()) / len(raw)
    if mean <= 1e-12:
        return dict.fromkeys(raw, 1.0)
    return {tag: v / mean for tag, v in raw.items()}


def compute_scores(working: dict[str, _Working], weights: Weights) -> dict[str, float]:
    total_w = weights.bandwidth + weights.cpu + weights.conn
    if total_w <= 0:
        return dict.fromkeys(working, 1.0)
    bw_n = _relative_to_mean({w.tag: w.bw_load for w in working.values()})
    cpu_n = _relative_to_mean({w.tag: w.cpu_load for w in working.values()})
    conn_n = _relative_to_mean({w.tag: w.conn_load for w in working.values()})
    return {
        tag: (
            weights.bandwidth * bw_n[tag]
            + weights.cpu * cpu_n[tag]
            + weights.conn * conn_n[tag]
        ) / total_w
        for tag in working
    }


def plan_moves(
    backends: list[BackendStat],
    keys: list[KeyStat],
    *,
    weights: Weights,
    spread_threshold: float,
    move_cap: int,
) -> list[Move]:
    working = {
        b.tag: _Working(tag=b.tag, bytes=float(b.recent_bytes), cpu=float(b.cpu_pct), conn=int(b.conn), cap=int(b.capacity))
        for b in backends
    }
    if len(working) < 2:
        return []

    keys_by_tag: dict[str, list[KeyStat]] = {}
    for k in keys:
        if k.current_tag in working:
            keys_by_tag.setdefault(k.current_tag, []).append(k)
    for tag in keys_by_tag:
        keys_by_tag[tag].sort(key=lambda k: k.weight, reverse=True)

    moves: list[Move] = []
    moved_ids: set = set()
    while len(moves) < move_cap:
        scores = compute_scores(working, weights)
        hot_tag = max(scores, key=lambda t: scores[t])
        if scores[hot_tag] - min(scores.values()) < spread_threshold:
            break
        chosen_key = None
        chosen_target = None
        for k in keys_by_tag.get(hot_tag, []):
            if k.key_id in moved_ids:
                continue
            target = _best_target(scores, working, k, hot_tag)
            if target is not None and scores[target] < scores[hot_tag]:
                chosen_key, chosen_target = k, target
                break
        if chosen_key is None:
            break
        working[hot_tag].bytes -= chosen_key.weight
        working[hot_tag].conn -= 1
        working[chosen_target].bytes += chosen_key.weight
        working[chosen_target].conn += 1
        moved_ids.add(chosen_key.key_id)
        moves.append(Move(key_id=chosen_key.key_id, from_tag=hot_tag, to_tag=chosen_target))
    return moves


def _best_target(scores: dict[str, float], working: dict[str, _Working], key: KeyStat, hot_tag: str) -> str | None:
    best = None
    best_score = None
    for tag in key.allowed_tags:
        if tag == hot_tag or tag not in working:
            continue
        if working[tag].conn >= working[tag].cap:
            continue
        s = scores[tag]
        if best is None or s < best_score:
            best, best_score = tag, s
    return best
