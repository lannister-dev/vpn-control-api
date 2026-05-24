"""Tests for the entry relay / whitelist gating logic inside _build_transport_routes.

The filter at line ~700 in subscription service.py decides which routes to include
based on the entry node's role and the plan's flags:
  - entry_node.role == 'whitelist_entry' → gated by plan.whitelist_enabled
  - entry_node.role == 'entry'          → gated by plan.entry_relay_enabled
  - no entry_node                       → always included (direct route)
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from services.nodes.constants import ROLE_ENTRY, ROLE_WHITELIST_ENTRY


def _make_plan(*, whitelist_enabled: bool = False, entry_relay_enabled: bool = False):
    return SimpleNamespace(whitelist_enabled=whitelist_enabled, entry_relay_enabled=entry_relay_enabled)


def _make_entry_node(*, role: str):
    return SimpleNamespace(id=uuid4(), role=role, is_active=True)


def _should_include(*, entry_node, plan) -> bool:
    """
    Replicates the filter logic from SubscriptionService._build_transport_routes
    for a single route with an entry node.
    """
    if entry_node is None:
        return True
    whitelist_enabled = bool(plan and getattr(plan, "whitelist_enabled", False))
    entry_relay_enabled = bool(plan and getattr(plan, "entry_relay_enabled", False))
    entry_role = getattr(entry_node, "role", "")
    if entry_role == ROLE_WHITELIST_ENTRY and not whitelist_enabled:
        return False
    if entry_role == ROLE_ENTRY and not entry_relay_enabled:
        return False
    return True


# ------------------------------------------------------------------
# Direct routes (no entry node) — always included
# ------------------------------------------------------------------

def test_direct_route_always_included():
    plan = _make_plan(whitelist_enabled=False, entry_relay_enabled=False)
    assert _should_include(entry_node=None, plan=plan) is True


# ------------------------------------------------------------------
# Whitelist entry routes — gated by whitelist_enabled
# ------------------------------------------------------------------

def test_whitelist_route_excluded_when_whitelist_disabled():
    entry = _make_entry_node(role=ROLE_WHITELIST_ENTRY)
    plan = _make_plan(whitelist_enabled=False, entry_relay_enabled=True)
    assert _should_include(entry_node=entry, plan=plan) is False


def test_whitelist_route_included_when_whitelist_enabled():
    entry = _make_entry_node(role=ROLE_WHITELIST_ENTRY)
    plan = _make_plan(whitelist_enabled=True, entry_relay_enabled=False)
    assert _should_include(entry_node=entry, plan=plan) is True


# ------------------------------------------------------------------
# Entry relay routes — gated by entry_relay_enabled
# ------------------------------------------------------------------

def test_entry_relay_route_excluded_when_relay_disabled():
    entry = _make_entry_node(role=ROLE_ENTRY)
    plan = _make_plan(whitelist_enabled=True, entry_relay_enabled=False)
    assert _should_include(entry_node=entry, plan=plan) is False


def test_entry_relay_route_included_when_relay_enabled():
    entry = _make_entry_node(role=ROLE_ENTRY)
    plan = _make_plan(whitelist_enabled=False, entry_relay_enabled=True)
    assert _should_include(entry_node=entry, plan=plan) is True


# ------------------------------------------------------------------
# Both flags enabled — both route types included
# ------------------------------------------------------------------

def test_both_flags_enabled_includes_both():
    plan = _make_plan(whitelist_enabled=True, entry_relay_enabled=True)
    wl = _make_entry_node(role=ROLE_WHITELIST_ENTRY)
    er = _make_entry_node(role=ROLE_ENTRY)
    assert _should_include(entry_node=wl, plan=plan) is True
    assert _should_include(entry_node=er, plan=plan) is True


# ------------------------------------------------------------------
# Both flags disabled — only direct routes survive
# ------------------------------------------------------------------

def test_both_flags_disabled_excludes_all_entry_routes():
    plan = _make_plan(whitelist_enabled=False, entry_relay_enabled=False)
    wl = _make_entry_node(role=ROLE_WHITELIST_ENTRY)
    er = _make_entry_node(role=ROLE_ENTRY)
    assert _should_include(entry_node=wl, plan=plan) is False
    assert _should_include(entry_node=er, plan=plan) is False
    assert _should_include(entry_node=None, plan=plan) is True


# ------------------------------------------------------------------
# Edge: plan is None (no plan attached to subscription)
# ------------------------------------------------------------------

def test_no_plan_excludes_entry_routes():
    wl = _make_entry_node(role=ROLE_WHITELIST_ENTRY)
    er = _make_entry_node(role=ROLE_ENTRY)
    assert _should_include(entry_node=wl, plan=None) is False
    assert _should_include(entry_node=er, plan=None) is False
    assert _should_include(entry_node=None, plan=None) is True
