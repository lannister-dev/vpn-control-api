from __future__ import annotations

import time
from unittest.mock import patch

from shared.reconciler.watchdog import ReconcilerWatchdog


def test_new_watchdog_is_alive_with_no_reconcilers():
    w = ReconcilerWatchdog()
    assert w.is_alive() is True
    assert w.statuses() == []


def test_register_seeds_last_tick_so_newly_registered_is_alive():
    w = ReconcilerWatchdog()
    w.register("loop_a")
    statuses = w.statuses()
    assert len(statuses) == 1
    assert statuses[0].name == "loop_a"
    assert statuses[0].alive is True
    assert w.is_alive() is True


def test_heartbeat_updates_silence_and_max_silence():
    w = ReconcilerWatchdog()
    w.heartbeat("loop_a", max_silence_sec=30)
    statuses = w.statuses()
    assert len(statuses) == 1
    assert statuses[0].silence_sec < 0.5
    assert statuses[0].max_silence_sec == 30
    assert statuses[0].alive is True


def test_is_not_alive_when_silence_exceeds_max():
    w = ReconcilerWatchdog()
    fake_now = [1000.0]

    def fake_monotonic():
        return fake_now[0]

    with patch.object(time, "monotonic", fake_monotonic):
        w.heartbeat("loop_a", max_silence_sec=60)
        assert w.is_alive() is True
        fake_now[0] = 1061.0  # 61 sec later — over the 60s limit
        assert w.is_alive() is False
        stale = [s for s in w.statuses() if not s.alive]
        assert [s.name for s in stale] == ["loop_a"]


def test_heartbeat_on_stale_reconciler_revives_it():
    w = ReconcilerWatchdog()
    fake_now = [1000.0]

    def fake_monotonic():
        return fake_now[0]

    with patch.object(time, "monotonic", fake_monotonic):
        w.heartbeat("loop_a", max_silence_sec=60)
        fake_now[0] = 1070.0
        assert w.is_alive() is False
        w.heartbeat("loop_a", max_silence_sec=60)
        assert w.is_alive() is True


def test_one_stale_reconciler_makes_watchdog_not_alive():
    w = ReconcilerWatchdog()
    fake_now = [1000.0]

    def fake_monotonic():
        return fake_now[0]

    with patch.object(time, "monotonic", fake_monotonic):
        w.heartbeat("a", max_silence_sec=60)
        w.heartbeat("b", max_silence_sec=60)
        fake_now[0] = 1070.0
        w.heartbeat("a", max_silence_sec=60)  # only a is refreshed
        assert w.is_alive() is False
        stale_names = {s.name for s in w.statuses() if not s.alive}
        assert stale_names == {"b"}


def test_unregister_removes_from_statuses():
    w = ReconcilerWatchdog()
    w.register("loop_a")
    w.register("loop_b")
    assert {s.name for s in w.statuses()} == {"loop_a", "loop_b"}
    w.unregister("loop_a")
    assert {s.name for s in w.statuses()} == {"loop_b"}


def test_heartbeat_clamps_max_silence_to_at_least_one_second():
    w = ReconcilerWatchdog()
    w.heartbeat("loop_a", max_silence_sec=0)
    statuses = w.statuses()
    assert statuses[0].max_silence_sec == 1.0
