from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from services.balancer.entry import EntryBalancer


def _balancer():
    settings = SimpleNamespace(entry_relay=SimpleNamespace(user_entry_bucket_seconds=0))
    return EntryBalancer(nats=None, settings=settings)


def _entry(*, node_id=None, is_active=True, is_enabled=True, is_draining=False, is_healthy=True, role="entry", zone="europe", region="de"):
    e = MagicMock()
    e.id = node_id or uuid4()
    e.is_active = is_active
    e.is_enabled = is_enabled
    e.is_draining = is_draining
    e.is_virtual = False
    e.role = role
    e.zone = zone
    e.region = region
    agent = MagicMock()
    agent.is_healthy = is_healthy
    e.agent_state = agent
    return e


def _backend(*, zone="europe", region="de"):
    b = MagicMock()
    b.zone = zone
    b.region = region
    return b


def test_live_explicit_entry_is_kept_when_others_busier():
    backend = _backend()
    chosen = _entry(node_id=uuid4())
    others = [_entry(node_id=uuid4()) for _ in range(3)]
    pool = {"europe": others}
    loads = {e.id: 50 for e in others}
    result = _balancer().select_entry_for_backend(
        backend_node=backend, current_entry=chosen, user_id=uuid4(),
        entries_by_zone=pool, entry_loads=loads,
    )
    assert result is chosen


def test_dead_entry_falls_back_to_pool():
    backend = _backend()
    draining_entry = _entry(is_draining=True)
    alt1, alt2 = _entry(node_id=uuid4()), _entry(node_id=uuid4())
    pool = {"europe": [alt1, alt2]}
    result = _balancer().select_entry_for_backend(
        backend_node=backend, current_entry=draining_entry, user_id=uuid4(), entries_by_zone=pool,
    )
    assert result in (alt1, alt2)


def test_no_entry_in_zone_returns_none():
    backend = _backend(zone="asia", region="sg")
    result = _balancer().select_entry_for_backend(
        backend_node=backend, current_entry=None, user_id=uuid4(), entries_by_zone={"europe": [_entry()]},
    )
    assert result is None


def test_same_user_stable_across_calls():
    backend = _backend()
    uid = uuid4()
    pool = {"europe": [_entry(node_id=uuid4()) for _ in range(5)]}
    b = _balancer()
    pick1 = b.select_entry_for_backend(
        backend_node=backend, current_entry=None, user_id=uid, entries_by_zone=pool,
    )
    pick2 = b.select_entry_for_backend(
        backend_node=backend, current_entry=None, user_id=uid, entries_by_zone=pool,
    )
    assert pick1 is pick2


def test_different_users_spread_across_pool():
    backend = _backend()
    pool = {"europe": [_entry(node_id=uuid4()) for _ in range(4)]}
    b = _balancer()
    picks = {
        b.select_entry_for_backend(
            backend_node=backend, current_entry=None, user_id=uuid4(), entries_by_zone=pool,
        ).id
        for _ in range(200)
    }
    assert len(picks) == 4
