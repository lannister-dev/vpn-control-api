from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.balancer.backend import BackendBalancer


def _node(name, *, is_enabled=True, is_draining=False):
    n = MagicMock()
    n.id = uuid4()
    n.name = name
    n.is_enabled = is_enabled
    n.is_draining = is_draining
    return n


def test_build_candidates_skips_disabled_and_draining():
    a, b, c = _node("a"), _node("b", is_enabled=False), _node("c", is_draining=True)
    nodes_by_id = {a.id: a, b.id: b, c.id: c}
    cands = BackendBalancer.build_candidates(
        key_id=uuid4(),
        allowed_backend_ids=[a.id, b.id, c.id],
        nodes_by_id=nodes_by_id,
        backend_loads={"backend-a": 7},
    )
    assert [c.tag for c in cands] == ["backend-a"]
    assert cands[0].load == 7


def test_backend_tiebreak_is_deterministic():
    kid, bid = uuid4(), uuid4()
    assert BackendBalancer._tiebreak(key_id=kid, backend_id=bid) == BackendBalancer._tiebreak(key_id=kid, backend_id=bid)


@pytest.mark.asyncio
async def test_assign_writes_least_loaded_when_no_current_tag():
    a, b = _node("a"), _node("b")
    nodes_by_id = {a.id: a, b.id: b}
    vpn_key = MagicMock()
    vpn_key.entry_routing_override_backend_tag = None
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=vpn_key)
    repo.update_by_id = AsyncMock()
    balancer = BackendBalancer(nats=None, vpn_key_repository=repo)

    loads = {"backend-a": 10, "backend-b": 0}
    chosen = await balancer.assign_key_backend(
        key_id=uuid4(), allowed_backend_ids=[a.id, b.id],
        nodes_by_id=nodes_by_id, backend_loads=loads,
    )
    assert chosen == "backend-b"
    repo.update_by_id.assert_awaited_once()
    assert loads["backend-b"] == 1


@pytest.mark.asyncio
async def test_assign_keeps_current_when_gap_small_and_skips_write():
    a, b = _node("a"), _node("b")
    nodes_by_id = {a.id: a, b.id: b}
    vpn_key = MagicMock()
    vpn_key.entry_routing_override_backend_tag = "backend-a"
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=vpn_key)
    repo.update_by_id = AsyncMock()
    balancer = BackendBalancer(nats=None, vpn_key_repository=repo)

    loads = {"backend-a": 1, "backend-b": 0}
    chosen = await balancer.assign_key_backend(
        key_id=uuid4(), allowed_backend_ids=[a.id, b.id],
        nodes_by_id=nodes_by_id, backend_loads=loads,
    )
    assert chosen == "backend-a"
    repo.update_by_id.assert_not_awaited()
