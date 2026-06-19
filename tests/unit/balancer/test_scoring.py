from __future__ import annotations

from services.balancer.scoring import (
    BackendStat,
    KeyStat,
    Weights,
    plan_moves,
)

ALL = frozenset({"lon", "zrh"})
W = Weights()


def _key(kid, tag, weight, allowed=ALL):
    return KeyStat(key_id=kid, current_tag=tag, allowed_tags=allowed, weight=float(weight))


def _plan(backends, keys, *, threshold=0.15, cap=15):
    return plan_moves(backends, keys, weights=W, spread_threshold=threshold, move_cap=cap)


def test_balanced_backends_yield_no_moves():
    backends = [
        BackendStat("lon", recent_bytes=10_000, cpu_pct=30, conn=3, capacity=100),
        BackendStat("zrh", recent_bytes=10_000, cpu_pct=30, conn=3, capacity=100),
    ]
    keys = [_key("a", "lon", 5_000), _key("b", "zrh", 5_000)]
    assert _plan(backends, keys) == []


def test_bandwidth_skew_with_equal_counts_moves_heaviest_first():
    backends = [
        BackendStat("lon", recent_bytes=50_000, cpu_pct=80, conn=3, capacity=100),
        BackendStat("zrh", recent_bytes=5_000, cpu_pct=20, conn=3, capacity=100),
    ]
    keys = [
        _key("lon-heavy", "lon", 30_000),
        _key("lon-mid", "lon", 15_000),
        _key("lon-light", "lon", 5_000),
        _key("zrh-1", "zrh", 3_000),
        _key("zrh-2", "zrh", 2_000),
    ]
    moves = _plan(backends, keys)
    assert moves, "expected rebalance when bandwidth is skewed despite equal connection counts"
    first = moves[0]
    assert first.from_tag == "lon"
    assert first.to_tag == "zrh"
    assert first.key_id == "lon-heavy"


def test_move_cap_is_respected():
    backends = [
        BackendStat("lon", recent_bytes=100_000, cpu_pct=90, conn=10, capacity=100),
        BackendStat("zrh", recent_bytes=0, cpu_pct=5, conn=0, capacity=100),
    ]
    keys = [_key(f"k{i}", "lon", 10_000) for i in range(10)]
    moves = _plan(backends, keys, cap=3)
    assert len(moves) == 3
    assert all(m.from_tag == "lon" and m.to_tag == "zrh" for m in moves)


def test_eligibility_blocks_ineligible_target():
    backends = [
        BackendStat("lon", recent_bytes=50_000, cpu_pct=80, conn=3, capacity=100),
        BackendStat("zrh", recent_bytes=2_000, cpu_pct=10, conn=3, capacity=100),
    ]
    keys = [
        _key("pinned", "lon", 40_000, allowed=frozenset({"lon"})),
        _key("movable", "lon", 8_000),
    ]
    moves = _plan(backends, keys)
    assert [m.key_id for m in moves] == ["movable"]


def test_full_target_has_no_headroom():
    backends = [
        BackendStat("lon", recent_bytes=50_000, cpu_pct=80, conn=3, capacity=100),
        BackendStat("zrh", recent_bytes=1_000, cpu_pct=5, conn=3, capacity=3),
    ]
    keys = [_key("heavy", "lon", 40_000)]
    assert _plan(backends, keys) == []


def test_single_backend_is_noop():
    backends = [BackendStat("lon", recent_bytes=99_000, cpu_pct=99, conn=9, capacity=100)]
    keys = [_key("a", "lon", 50_000)]
    assert _plan(backends, keys) == []
