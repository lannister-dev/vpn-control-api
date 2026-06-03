from __future__ import annotations

from uuid import uuid4

from services.balancer.policy import BalancerPolicy
from services.balancer.types import KeyLoad, NodeLoad
from services.config import BalancerConfig

LON = uuid4()
ZRH = uuid4()


def compute_plan(nodes, keys, c):
    return BalancerPolicy(c).plan(nodes, keys)


def node(nid, name, bps, sessions=0, cpu=10.0, capacity=100.0):
    return NodeLoad(node_id=nid, name=name, bps=bps, sessions=sessions, cpu_pct=cpu, capacity=capacity)


def key(bps, current, eligible):
    return KeyLoad(key_id=uuid4(), bps=bps, current_backend_id=current, eligible_backend_ids=frozenset(eligible))


def cfg(**kw):
    base = dict(enabled=True, dead_zone=0.12, move_fraction=0.5, max_moves_per_tick=50)
    base.update(kw)
    return BalancerConfig(**base)


def test_single_node_noop():
    plan = compute_plan([node(LON, "lon", 1000)], [], cfg())
    assert plan.is_noop and plan.skipped_reason == "need_two_nodes"


def test_balanced_no_moves():
    nodes = [node(LON, "lon", 1000, sessions=10), node(ZRH, "zrh", 1000, sessions=10)]
    keys = [key(100, LON, [LON, ZRH]) for _ in range(5)]
    assert compute_plan(nodes, keys, cfg()).is_noop


def test_bootstrap_empty_new_node():
    nodes = [node(LON, "lon", 10_000, sessions=20), node(ZRH, "zrh", 0, sessions=0)]
    keys = [key(500, LON, [LON, ZRH]) for _ in range(20)]
    plan = compute_plan(nodes, keys, cfg())
    assert plan.moves, "should fill the empty node"
    assert all(m.to_backend_id == ZRH and m.from_backend_id == LON for m in plan.moves)
    assert all(m.to_tag == "backend-zrh" for m in plan.moves)


def test_respects_eligibility():
    nodes = [node(LON, "lon", 10_000, sessions=20), node(ZRH, "zrh", 0)]
    keys = [key(500, LON, [LON]) for _ in range(20)]
    assert compute_plan(nodes, keys, cfg()).is_noop


def test_cpu_full_sink_excluded():
    nodes = [node(LON, "lon", 10_000, sessions=20), node(ZRH, "zrh", 0, cpu=95.0)]
    keys = [key(500, LON, [LON, ZRH]) for _ in range(20)]
    assert compute_plan(nodes, keys, cfg(cpu_full_pct=85.0)).is_noop


def test_dead_zone_blocks_small_imbalance():
    nodes = [node(LON, "lon", 1100, sessions=11), node(ZRH, "zrh", 900, sessions=9)]
    keys = [key(50, LON, [LON, ZRH]) for _ in range(22)]
    assert compute_plan(nodes, keys, cfg(dead_zone=0.30)).is_noop


def test_capacity_weighting_targets_bigger_node():
    nodes = [node(LON, "lon", 8000, sessions=8, capacity=100), node(ZRH, "zrh", 0, capacity=300)]
    keys = [key(200, LON, [LON, ZRH]) for _ in range(40)]
    plan = compute_plan(nodes, keys, cfg(move_fraction=1.0, max_moves_per_tick=100))
    moved = sum(m.bps for m in plan.moves)
    assert moved >= 4000, f"moved={moved}"


def test_does_not_overshoot_with_whale():
    nodes = [node(LON, "lon", 6000, sessions=10), node(ZRH, "zrh", 4000, sessions=10)]
    keys = [key(5000, LON, [LON, ZRH])] + [key(100, LON, [LON, ZRH]) for _ in range(10)]
    plan = compute_plan(nodes, keys, cfg(dead_zone=0.05, move_fraction=0.5))
    whale_moved = any(m.bps == 5000 for m in plan.moves)
    assert not whale_moved, "must not move the whale for a small gap"


def test_max_moves_cap():
    nodes = [node(LON, "lon", 100_000, sessions=100), node(ZRH, "zrh", 0)]
    keys = [key(100, LON, [LON, ZRH]) for _ in range(500)]
    plan = compute_plan(nodes, keys, cfg(max_moves_per_tick=10))
    assert len(plan.moves) == 10
